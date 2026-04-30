import pytest

from vcse.trust.tiers import can_transition, validate_transition
from vcse.trust.errors import TrustError


def test_tier_transitions_valid_chain() -> None:
    assert can_transition("T0_CANDIDATE", "T1_PROVENANCED")
    assert can_transition("T1_PROVENANCED", "T2_SOURCE_TRUSTED")
    assert can_transition("T2_SOURCE_TRUSTED", "T3_CROSS_SUPPORTED")
    assert can_transition("T3_CROSS_SUPPORTED", "T4_VERIFIER_CONSISTENT")
    assert can_transition("T4_VERIFIER_CONSISTENT", "T5_CERTIFIED")


def test_invalid_tier_skip_rejected() -> None:
    with pytest.raises(TrustError):
        validate_transition("T0_CANDIDATE", "T3_CROSS_SUPPORTED")
