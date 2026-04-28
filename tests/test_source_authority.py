from vcse.trust.scorer import SourceAuthorityRegistry


def test_source_authority_scoring_works() -> None:
    registry = SourceAuthorityRegistry()
    assert registry.score("official_government") > registry.score("local_file")
    assert registry.score("unknown_source") == registry.score("unknown")
