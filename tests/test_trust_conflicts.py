from vcse.trust.conflict import detect_conflicts


def test_equality_conflict_detected() -> None:
    conflicts = detect_conflicts(
        [
            {"claim_id": "c1", "subject": "x", "relation": "equals", "object": "3"},
            {"claim_id": "c2", "subject": "x", "relation": "equals", "object": "4"},
        ]
    )
    assert any(item.conflict_type == "EQUALITY_CONFLICT" for item in conflicts)


def test_numeric_range_conflict_detected() -> None:
    conflicts = detect_conflicts(
        [
            {"claim_id": "c1", "subject": "x", "relation": ">", "object": "10"},
            {"claim_id": "c2", "subject": "x", "relation": "<=", "object": "10"},
        ]
    )
    assert any(item.conflict_type == "NUMERIC_RANGE_CONFLICT" for item in conflicts)


def test_functional_relation_conflict_detected() -> None:
    conflicts = detect_conflicts(
        [
            {"claim_id": "c1", "subject": "org", "relation": "ceo", "object": "Alice"},
            {"claim_id": "c2", "subject": "org", "relation": "ceo", "object": "Bob"},
        ]
    )
    assert any(item.conflict_type == "FUNCTIONAL_RELATION_CONFLICT" for item in conflicts)
