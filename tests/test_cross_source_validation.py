from vcse.trust.promoter import ClaimClusterer, CrossSourceValidator


def test_independent_sources_increase_support_count() -> None:
    claims = [
        {"subject": "a", "relation": "is_a", "object": "b", "source_id": "standards_body"},
        {"subject": "a", "relation": "is_a", "object": "b", "source_id": "academic_reference"},
    ]
    cluster = ClaimClusterer().cluster(claims)[0]
    assert cluster.support_count == 2
    assert CrossSourceValidator().support_score(cluster) > 0.0
