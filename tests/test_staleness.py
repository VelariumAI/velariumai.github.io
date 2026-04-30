from vcse.trust.policy import StalenessPolicy
from vcse.trust.staleness import evaluate_staleness


def test_stale_volatile_claim_marked_stale() -> None:
    result = evaluate_staleness(
        {
            "subject": "btc",
            "relation": "price",
            "object": "100000",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        policy=StalenessPolicy(freshness_days=365),
    )
    assert result.stale is True


def test_stable_claim_not_stale_too_early() -> None:
    result = evaluate_staleness(
        {
            "subject": "socrates",
            "relation": "is_a",
            "object": "mortal",
            "created_at": "2026-04-20T00:00:00+00:00",
        },
        policy=StalenessPolicy(freshness_days=365),
    )
    assert result.stale is False
