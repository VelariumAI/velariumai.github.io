"""Knowledge claim normalization."""

from __future__ import annotations

import re

from vcse.interaction.normalizer import SemanticNormalizer
from vcse.knowledge.pack_model import KnowledgeClaim


class KnowledgeNormalizer:
    def __init__(self, external_synonyms: list[tuple[str, str]] | None = None) -> None:
        self.semantic_normalizer = SemanticNormalizer(external_synonyms=external_synonyms or [])

    def normalize_claim(self, claim: KnowledgeClaim) -> KnowledgeClaim:
        subject = _normalize_entity(claim.subject)
        relation = _normalize_relation(claim.relation)
        obj = _normalize_object(claim.object)
        return KnowledgeClaim(
            subject=subject,
            relation=relation,
            object=obj,
            provenance=claim.provenance,
            qualifiers=dict(sorted(claim.qualifiers.items())),
            confidence=claim.confidence,
        )


def _normalize_relation(value: str) -> str:
    relation = value.strip().lower().replace(" ", "_")
    aliases = {
        "is": "is_a",
        "isa": "is_a",
        "partof": "part_of",
    }
    return aliases.get(relation, relation)


def _normalize_entity(value: str) -> str:
    clean = " ".join(str(value).strip().split())
    if not clean:
        return ""
    if clean.islower():
        return clean
    return clean[0].upper() + clean[1:]


def _normalize_object(value: str) -> str:
    clean = " ".join(str(value).strip().split())
    clean = re.sub(r"\s+", "_", clean)
    return clean
