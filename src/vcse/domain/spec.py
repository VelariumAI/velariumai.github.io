"""Domain specification dataclasses."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RelationSpec:
    relation: str
    canonical: str
    inverse: str | None
    domain: str
    range: str
    functional: bool
    symmetric: bool
    transitive: bool
    shard: str


@dataclass(frozen=True)
class QueryPatternSpec:
    pattern: str
    relation: str
    query_type: str
    subject_slot: str
    object_slot: str | None


@dataclass(frozen=True)
class ShardRuleSpec:
    shard_id: str
    relations: tuple[str, ...]


@dataclass(frozen=True)
class InferenceRuleSpec:
    rule_id: str
    output_relation: str
    required_relations: tuple[str, ...]
    max_hops: int


@dataclass(frozen=True)
class BenchmarkTemplateSpec:
    relation: str
    template: str
    expected_slot: str


@dataclass(frozen=True)
class DomainSpec:
    domain_id: str
    name: str
    version: str
    relations: tuple[RelationSpec, ...]
    query_patterns: tuple[QueryPatternSpec, ...]
    shard_rules: tuple[ShardRuleSpec, ...]
    inference_rules: tuple[InferenceRuleSpec, ...]
    benchmark_templates: tuple[BenchmarkTemplateSpec, ...]
