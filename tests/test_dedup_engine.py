from __future__ import annotations

from vcse.knowledge.dedup import deduplicate_claims
from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgeProvenance


def _claim(subject: str, relation: str, obj: str, source_id: str) -> KnowledgeClaim:
    return KnowledgeClaim(
        subject=subject,
        relation=relation,
        object=obj,
        provenance=KnowledgeProvenance(
            source_id=source_id,
            source_type="test",
            location="loc",
            evidence_text="evidence",
        ),
    )


def test_deduplicate_claims_returns_unique_and_duplicates_with_merged_provenance() -> None:
    existing = [_claim("Paris", "capital_of", "France", "existing-src")]
    new_claims = [
        _claim("Paris", "capital_of", "France", "dup-1"),
        _claim("Paris", "capital_of", "France", "dup-2"),
        _claim("Berlin", "capital_of", "Germany", "new-1"),
    ]
    result = deduplicate_claims(existing, new_claims)

    assert [claim.key for claim in result.unique_claims] == ["Berlin|capital_of|Germany"]
    assert [claim.provenance.source_id for claim in result.duplicates_detected] == ["dup-1", "dup-2"]
    merged = result.merged_provenance_map["Paris|capital_of|France"]
    assert [item.source_id for item in merged] == ["existing-src", "dup-1", "dup-2"]


def test_deduplicate_claims_is_deterministic() -> None:
    existing = [_claim("Paris", "capital_of", "France", "existing-src")]
    new_claims = [
        _claim("Rome", "capital_of", "Italy", "new-1"),
        _claim("Paris", "capital_of", "France", "dup-1"),
    ]
    first = deduplicate_claims(existing, new_claims)
    second = deduplicate_claims(existing, new_claims)

    assert [claim.key for claim in first.unique_claims] == [claim.key for claim in second.unique_claims]
    assert [claim.key for claim in first.duplicates_detected] == [claim.key for claim in second.duplicates_detected]
    assert {
        key: [p.source_id for p in value]
        for key, value in first.merged_provenance_map.items()
    } == {
        key: [p.source_id for p in value]
        for key, value in second.merged_provenance_map.items()
    }
