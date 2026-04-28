"""Thin adapter over KnowledgeNormalizer for CAKE claims."""

from __future__ import annotations

from vcse.knowledge.normalizer import KnowledgeNormalizer
from vcse.knowledge.pack_model import KnowledgeClaim


class CakeNormalizerAdapter:
    """Normalizes claims using the existing KnowledgeNormalizer. Zero duplication."""

    def __init__(self) -> None:
        self._normalizer = KnowledgeNormalizer()

    def normalize(self, claims: list[KnowledgeClaim]) -> list[KnowledgeClaim]:
        return [self._normalizer.normalize_claim(c) for c in claims]