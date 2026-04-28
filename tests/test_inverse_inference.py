from __future__ import annotations

from vcse.inference.inverse import infer_inverse_claims
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


def test_inverse_inference_correctness_has_capital_to_capital_of() -> None:
    claims = [_claim("France", "has_capital", "Paris")]
    inferred = infer_inverse_claims(claims)
    assert len(inferred) == 1
    assert inferred[0].subject == "Paris"
    assert inferred[0].relation == "capital_of"
    assert inferred[0].object == "France"
    assert inferred[0].derived_from == "France|has_capital|Paris"
    assert inferred[0].rule == "inverse_relation"
    assert inferred[0].trust_tier == "T1_INFERRED"


def test_inverse_inference_does_not_duplicate_existing_inverse() -> None:
    claims = [
        _claim("France", "has_capital", "Paris"),
        _claim("Paris", "capital_of", "France"),
    ]
    inferred = infer_inverse_claims(claims)
    assert inferred == []


def test_inverse_inference_is_deterministic_ordered() -> None:
    claims = [
        _claim("France", "has_capital", "Paris"),
        _claim("Italy", "has_capital", "Rome"),
    ]
    first = infer_inverse_claims(claims)
    second = infer_inverse_claims(claims)
    assert [item.key for item in first] == [item.key for item in second]
    assert [item.key for item in first] == [
        "Paris|capital_of|France",
        "Rome|capital_of|Italy",
    ]


def test_inverse_inference_has_no_side_effects() -> None:
    claims = [_claim("France", "has_capital", "Paris")]
    before = [(c.subject, c.relation, c.object, c.key) for c in claims]
    _ = infer_inverse_claims(claims)
    after = [(c.subject, c.relation, c.object, c.key) for c in claims]
    assert before == after
