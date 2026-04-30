"""Composite retrieval scoring utilities."""

from __future__ import annotations

from dataclasses import dataclass

from vcse.index.bm25 import BM25Scorer
from vcse.index.index import IndexedArtifact


@dataclass(frozen=True)
class ScoringWeights:
    exact_token_bonus: float = 0.4
    normalized_match_bonus: float = 0.2
    relation_match_bonus: float = 0.25


DEFAULT_ARTIFACT_TYPE_WEIGHTS = {
    "synonym": 1.2,
    "parser_pattern": 1.2,
    "relation_schema": 1.0,
    "ingestion_template": 1.0,
    "generation_template": 1.1,
    "proposer_rule": 1.1,
    "clarification_rule": 1.0,
    "renderer_template": 1.0,
    "verifier_rule_stub": 0.8,
}


def score_artifact(
    artifact: IndexedArtifact,
    query_tokens: list[str],
    normalized_tokens: list[str],
    relation_hints: set[str],
    bm25: BM25Scorer,
    weights: ScoringWeights | None = None,
    artifact_type_weights: dict[str, float] | None = None,
) -> float:
    if weights is None:
        weights = ScoringWeights()
    if artifact_type_weights is None:
        artifact_type_weights = DEFAULT_ARTIFACT_TYPE_WEIGHTS

    bm25_score = bm25.score(query_tokens, artifact)
    if bm25_score <= 0 and not query_tokens:
        return 0.0

    query_set = set(query_tokens)
    norm_set = set(normalized_tokens)
    token_set = set(artifact.feature_vector.keys())
    overlap = len(query_set & token_set)
    exact_bonus = (overlap / max(1, len(query_set))) * weights.exact_token_bonus

    normalized_overlap = len(norm_set & token_set)
    normalized_bonus = (normalized_overlap / max(1, len(norm_set))) * weights.normalized_match_bonus

    relation_bonus = 0.0
    if relation_hints and set(artifact.relations) & relation_hints:
        relation_bonus = weights.relation_match_bonus

    type_weight = artifact_type_weights.get(artifact.artifact_type, 1.0)
    priority_bonus = 1.0 / max(1, artifact.priority)

    total = (bm25_score + exact_bonus + normalized_bonus + relation_bonus + priority_bonus) * type_weight
    return round(total, 8)
