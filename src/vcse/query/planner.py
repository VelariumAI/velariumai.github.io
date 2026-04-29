"""Opt-in shard-aware query planning for a fixed set of query classes."""

from __future__ import annotations

from dataclasses import dataclass

from vcse.interaction.query_normalizer import NormalizedQuery


@dataclass(frozen=True)
class QueryPlan:
    subject: str
    target_relation: str
    required_shards: tuple[str, ...]
    required_indexes: tuple[str, ...]
    inference_rules: tuple[str, ...]
    max_hops: int
    fallback_allowed: bool = True


class QueryPlanner:
    _RELATION_TO_SHARD = {
        "has_capital": "geography.capitals",
        "capital_of": "geography.capitals",
        "located_in_country": "geography.location",
        "located_in_region": "geography.location",
        "part_of": "geography.location",
        "uses_currency": "geography.currency",
        "language_of": "geography.language",
        "has_country_code": "geography.codes",
    }

    _SUPPORTED_RELATIONS = set(_RELATION_TO_SHARD)

    def plan(self, normalized_query: NormalizedQuery | None) -> QueryPlan | None:
        if normalized_query is None:
            return None
        relation = normalized_query.relation.strip().lower()
        if relation == "capital_of":
            relation = "has_capital"
        if relation not in self._SUPPORTED_RELATIONS:
            return None
        inference_rules = ("transitive",) if relation in {"located_in_region", "part_of"} else tuple()
        max_hops = 2 if "transitive" in inference_rules else 0
        return QueryPlan(
            subject=normalized_query.subject.strip(),
            target_relation=relation,
            required_shards=(self._RELATION_TO_SHARD[relation],),
            required_indexes=("idx_claim_shard_relation", "idx_claim_subject_relation_ids"),
            inference_rules=inference_rules,
            max_hops=max_hops,
            fallback_allowed=True,
        )

    def plan_for_claim(self, subject: str, relation: str) -> QueryPlan | None:
        rel = relation.strip().lower()
        if rel == "capital_of":
            rel = "has_capital"
        if rel not in self._SUPPORTED_RELATIONS:
            return None
        inference_rules = ("transitive",) if rel in {"located_in_region", "part_of"} else tuple()
        max_hops = 2 if "transitive" in inference_rules else 0
        return QueryPlan(
            subject=subject.strip(),
            target_relation=rel,
            required_shards=(self._RELATION_TO_SHARD[rel],),
            required_indexes=("idx_claim_shard_relation", "idx_claim_subject_relation_ids"),
            inference_rules=inference_rules,
            max_hops=max_hops,
            fallback_allowed=True,
        )
