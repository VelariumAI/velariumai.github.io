from vcse.trust.policy import TrustPolicy
from vcse.trust.promoter import TrustPromoter


def test_promoter_explains_blockers() -> None:
    promoter = TrustPromoter(policy=TrustPolicy(require_gauntlet_pass=True))
    decision = promoter.evaluate_claim(
        {
            "claim_id": "c1",
            "subject": "a",
            "relation": "is_a",
            "object": "b",
            "source_id": "unknown",
            "provenance": {"source_id": "unknown"},
            "created_at": "2026-04-20T00:00:00+00:00",
        },
        support_count=1,
        conflict_count=0,
    )
    assert decision.blocking_issues
    assert any("threshold" in item or "support" in item or "gauntlet" in item for item in decision.blocking_issues)
