from __future__ import annotations

import time

from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgeProvenance
from vcse.semantic.region_builder import build_regions
from vcse.semantic.runtime_regions import RuntimeRegionIndex


def _claim(subject: str, relation: str, obj: str, qualifiers: dict[str, str] | None = None) -> KnowledgeClaim:
    return KnowledgeClaim(
        subject=subject,
        relation=relation,
        object=obj,
        qualifiers=qualifiers or {},
        provenance=KnowledgeProvenance(
            source_id="src",
            source_type="test",
            location="unit",
            evidence_text="evidence",
        ),
    )


def test_semantic_regions_are_deterministic() -> None:
    claims = [
        _claim("France", "has_capital", "Paris"),
        _claim("Germany", "has_capital", "Berlin"),
        _claim("Paris", "capital_of", "France"),
    ]

    first = build_regions(claims)
    second = build_regions(claims)

    first_ids = sorted(region.region_id for region in first)
    second_ids = sorted(region.region_id for region in second)
    assert first_ids == second_ids


def test_grouping_collects_same_relation_into_one_region() -> None:
    claims = [
        _claim("France", "has_capital", "Paris"),
        _claim("Germany", "has_capital", "Berlin"),
    ]

    regions = build_regions(claims)

    assert len(regions) == 1
    region = regions[0]
    assert region.relations == {"has_capital"}
    assert region.subjects == {"France", "Germany"}
    assert region.size == 2


def test_existing_region_id_is_stable_when_unrelated_claim_is_added() -> None:
    baseline = [
        _claim("France", "has_capital", "Paris"),
        _claim("Germany", "has_capital", "Berlin"),
    ]
    expanded = baseline + [_claim("Cat", "is_a", "Animal")]

    baseline_index = RuntimeRegionIndex(baseline)
    expanded_index = RuntimeRegionIndex(expanded)

    baseline_region = baseline_index.get_region_by_relation("has_capital")
    expanded_region = expanded_index.get_region_by_relation("has_capital")
    assert baseline_region.region_id == expanded_region.region_id


def test_region_build_performance_for_5k_claims() -> None:
    claims = [_claim(f"Country{i}", "has_capital", f"Capital{i}") for i in range(6000)]

    start = time.perf_counter()
    regions = build_regions(claims)
    elapsed = time.perf_counter() - start

    assert len(regions) == 1
    assert elapsed < 2.5


def test_inverse_relations_are_distinct_regions() -> None:
    claims = [
        _claim("France", "has_capital", "Paris"),
        _claim("Paris", "capital_of", "France"),
    ]

    regions = build_regions(claims)
    assert len(regions) == 2

    by_relation = {next(iter(region.relations)): region for region in regions}
    assert by_relation["has_capital"].region_id != by_relation["capital_of"].region_id
