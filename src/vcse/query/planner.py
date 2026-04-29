"""Opt-in shard-aware query planning for a fixed set of query classes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

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
    _FALLBACK_RELATION_TO_SHARD = {
        "has_capital": "geography.capitals",
        "capital_of": "geography.capitals",
        "located_in_country": "geography.location",
        "located_in_region": "geography.location",
        "part_of": "geography.location",
        "uses_currency": "geography.currency",
        "language_of": "geography.language",
        "has_country_code": "geography.codes",
    }
    _FALLBACK_SUPPORTED_RELATIONS = set(_FALLBACK_RELATION_TO_SHARD)
    _FALLBACK_TRANSITIVE_RELATIONS = {"located_in_region", "part_of"}

    def __init__(self) -> None:
        self._relation_to_shard = dict(self._FALLBACK_RELATION_TO_SHARD)
        self._supported_relations = set(self._FALLBACK_SUPPORTED_RELATIONS)
        self._transitive_relations = set(self._FALLBACK_TRANSITIVE_RELATIONS)
        self._load_domain_metadata()

    def _load_domain_metadata(self) -> None:
        candidates = (
            Path("domains/geography.yaml"),
            Path(__file__).resolve().parents[3] / "domains" / "geography.yaml",
        )
        for candidate in candidates:
            if not candidate.exists():
                continue
            try:
                payload = _load_spec_payload(candidate)
                relations = payload.get("relations", [])
                inference_rules = payload.get("inference_rules", [])
                if not isinstance(relations, list) or not isinstance(inference_rules, list):
                    return
            except Exception:
                return
            relation_to_shard = {
                str(item.get("relation", "")).strip(): str(item.get("shard", "")).strip() for item in relations if isinstance(item, dict)
            }
            # Preserve existing supported behavior for this release.
            self._relation_to_shard.update({k: v for k, v in relation_to_shard.items() if k in self._supported_relations})
            for rule in inference_rules:
                if not isinstance(rule, dict):
                    continue
                if str(rule.get("rule_id", "")).strip() == "transitive_location_containment":
                    required = rule.get("required_relations", [])
                    if isinstance(required, list):
                        self._transitive_relations.update(rel for rel in required if rel in self._supported_relations)
            return

    def plan(self, normalized_query: NormalizedQuery | None) -> QueryPlan | None:
        if normalized_query is None:
            return None
        relation = normalized_query.relation.strip().lower()
        if relation == "capital_of":
            relation = "has_capital"
        if relation not in self._supported_relations:
            return None
        inference_rules = ("transitive",) if relation in self._transitive_relations else tuple()
        max_hops = 2 if "transitive" in inference_rules else 0
        return QueryPlan(
            subject=normalized_query.subject.strip(),
            target_relation=relation,
            required_shards=(self._relation_to_shard[relation],),
            required_indexes=("idx_claim_shard_relation", "idx_claim_subject_relation_ids"),
            inference_rules=inference_rules,
            max_hops=max_hops,
            fallback_allowed=True,
        )

    def plan_for_claim(self, subject: str, relation: str) -> QueryPlan | None:
        rel = relation.strip().lower()
        if rel == "capital_of":
            rel = "has_capital"
        if rel not in self._supported_relations:
            return None
        inference_rules = ("transitive",) if rel in self._transitive_relations else tuple()
        max_hops = 2 if "transitive" in inference_rules else 0
        return QueryPlan(
            subject=subject.strip(),
            target_relation=rel,
            required_shards=(self._relation_to_shard[rel],),
            required_indexes=("idx_claim_shard_relation", "idx_claim_subject_relation_ids"),
            inference_rules=inference_rules,
            max_hops=max_hops,
            fallback_allowed=True,
        )


def _load_spec_payload(path: Path) -> dict[str, object]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text())
    else:
        import yaml  # type: ignore[import-not-found]

        data = yaml.safe_load(path.read_text())
    return data if isinstance(data, dict) else {}
