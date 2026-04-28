from __future__ import annotations

from vcse.inference.transitive import infer_transitive_claims
from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgeProvenance


def _claim(subject: str, relation: str, obj: str) -> KnowledgeClaim:
    return KnowledgeClaim(
        subject=subject,
        relation=relation,
        object=obj,
        provenance=KnowledgeProvenance(
            source_id="src",
            source_type="test",
            location="unit",
            evidence_text="evidence",
        ),
    )


def test_transitive_location_chain_country_part_of_region() -> None:
    claims = [
        _claim("Paris", "located_in_country", "France"),
        _claim("France", "part_of", "Europe"),
    ]
    inferred = infer_transitive_claims(claims)
    assert len(inferred) == 1
    assert inferred[0].subject == "Paris"
    assert inferred[0].relation == "located_in_region"
    assert inferred[0].object == "Europe"
    assert inferred[0].derived_from == (
        "Paris|located_in_country|France",
        "France|part_of|Europe",
    )
    assert inferred[0].rule == "transitive_location_containment"
    assert inferred[0].trust_tier == "T1_INFERRED"


def test_transitive_location_chain_country_region_region() -> None:
    claims = [
        _claim("Paris", "located_in_country", "France"),
        _claim("France", "located_in_region", "Europe"),
    ]
    inferred = infer_transitive_claims(claims)
    assert len(inferred) == 1
    assert inferred[0].key == "Paris|located_in_region|Europe"


def test_transitive_inference_does_not_duplicate_explicit_claim() -> None:
    claims = [
        _claim("Paris", "located_in_country", "France"),
        _claim("France", "part_of", "Europe"),
        _claim("Paris", "located_in_region", "Europe"),
    ]
    inferred = infer_transitive_claims(claims)
    assert inferred == []


def test_transitive_inference_is_deterministic() -> None:
    claims = [
        _claim("Paris", "located_in_country", "France"),
        _claim("France", "part_of", "Europe"),
        _claim("Berlin", "located_in_country", "Germany"),
        _claim("Germany", "located_in_region", "Europe"),
    ]
    first = infer_transitive_claims(claims)
    second = infer_transitive_claims(claims)
    assert [item.key for item in first] == [item.key for item in second]
    assert [item.key for item in first] == [
        "Paris|located_in_region|Europe",
        "Berlin|located_in_region|Europe",
    ]


def test_transitive_inference_has_no_side_effects() -> None:
    claims = [
        _claim("Paris", "located_in_country", "France"),
        _claim("France", "part_of", "Europe"),
    ]
    before = [(c.subject, c.relation, c.object, c.key) for c in claims]
    _ = infer_transitive_claims(claims)
    after = [(c.subject, c.relation, c.object, c.key) for c in claims]
    assert before == after
