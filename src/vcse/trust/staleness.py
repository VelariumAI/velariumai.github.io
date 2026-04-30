"""Staleness detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from vcse.trust.policy import StalenessPolicy


_VOLATILE_RELATIONS = {
    "price": 1,
    "current_status": 7,
    "population": 30,
    "ceo": 14,
    "president": 14,
}


@dataclass(frozen=True)
class StalenessResult:
    stale: bool
    reason: str
    age_days: int
    freshness_days: int


def evaluate_staleness(claim: dict, policy: StalenessPolicy | None = None) -> StalenessResult:
    policy = policy or StalenessPolicy()
    relation = str(claim.get("relation", ""))
    created_at = str(claim.get("created_at", ""))
    if not created_at:
        return StalenessResult(stale=False, reason="missing timestamp", age_days=0, freshness_days=policy.freshness_days)
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except Exception:
        return StalenessResult(stale=False, reason="invalid timestamp", age_days=0, freshness_days=policy.freshness_days)
    now = datetime.now(timezone.utc)
    age_days = max(0, int((now - created.astimezone(timezone.utc)).days))
    freshness = _VOLATILE_RELATIONS.get(relation, policy.freshness_for(relation))
    stale = age_days > freshness
    reason = "stale" if stale else "fresh"
    return StalenessResult(stale=stale, reason=reason, age_days=age_days, freshness_days=freshness)
