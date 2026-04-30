"""Trust tier definitions and lifecycle guards."""

from __future__ import annotations

from dataclasses import dataclass


TIERS = (
    "T0_CANDIDATE",
    "T1_PROVENANCED",
    "T2_SOURCE_TRUSTED",
    "T3_CROSS_SUPPORTED",
    "T4_VERIFIER_CONSISTENT",
    "T5_CERTIFIED",
    "T6_DEPRECATED",
    "T7_CONFLICTED",
)

FLAGS = ("STALE", "CONFLICTED", "DEPRECATED", "SUPERSEDED")

_ALLOWED_FORWARD = {
    "T0_CANDIDATE": {"T1_PROVENANCED"},
    "T1_PROVENANCED": {"T2_SOURCE_TRUSTED"},
    "T2_SOURCE_TRUSTED": {"T3_CROSS_SUPPORTED"},
    "T3_CROSS_SUPPORTED": {"T4_VERIFIER_CONSISTENT"},
    "T4_VERIFIER_CONSISTENT": {"T5_CERTIFIED"},
    "T5_CERTIFIED": set(),
    "T6_DEPRECATED": set(),
    "T7_CONFLICTED": set(),
}


@dataclass(frozen=True)
class TierTransition:
    current_tier: str
    next_tier: str


def is_valid_tier(value: str) -> bool:
    return value in TIERS


def can_transition(current_tier: str, next_tier: str) -> bool:
    if current_tier == next_tier:
        return True
    if current_tier in {"T7_CONFLICTED", "T6_DEPRECATED"}:
        return False
    if next_tier in {"T7_CONFLICTED", "T6_DEPRECATED"}:
        return True
    return next_tier in _ALLOWED_FORWARD.get(current_tier, set())


def validate_transition(current_tier: str, next_tier: str) -> None:
    from vcse.trust.errors import TrustError

    if not is_valid_tier(current_tier) or not is_valid_tier(next_tier):
        raise TrustError("INVALID_TIER", f"invalid tier transition {current_tier} -> {next_tier}")
    if not can_transition(current_tier, next_tier):
        raise TrustError("INVALID_TIER_TRANSITION", f"cannot transition {current_tier} -> {next_tier}")
