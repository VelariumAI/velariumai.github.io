from vcse.trust.promoter import ClaimClusterer


def test_same_source_duplicate_does_not_increase_support_count() -> None:
    claims = [
        {"subject": "a", "relation": "is_a", "object": "b", "source_id": "local_file"},
        {"subject": "a", "relation": "is_a", "object": "b", "source_id": "local_file"},
    ]
    clusters = ClaimClusterer().cluster(claims)
    assert len(clusters) == 1
    assert clusters[0].support_count == 1
