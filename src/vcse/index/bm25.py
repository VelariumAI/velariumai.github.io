"""Deterministic BM25 scoring."""

from __future__ import annotations

import math

from vcse.index.index import IndexedArtifact, SymbolicIndex


class BM25Scorer:
    def __init__(self, index: SymbolicIndex, k1: float = 1.2, b: float = 0.75) -> None:
        self.index = index
        self.k1 = k1
        self.b = b

    def score(self, query_tokens: list[str], artifact: IndexedArtifact) -> float:
        if not query_tokens or artifact.length <= 0:
            return 0.0

        total_docs = max(1, self.index.artifact_count)
        avg_len = self.index.average_doc_length or 1.0
        score = 0.0
        for token in query_tokens:
            tf = artifact.feature_vector.get(token, 0)
            if tf == 0:
                continue
            df = self.index.document_frequency.get(token, 0)
            idf = math.log(1 + ((total_docs - df + 0.5) / (df + 0.5)))
            denom = tf + self.k1 * (1 - self.b + self.b * (artifact.length / avg_len))
            score += idf * ((tf * (self.k1 + 1)) / denom)
        return score
