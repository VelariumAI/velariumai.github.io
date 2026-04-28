"""Controlled promotion of stable inferred claims into candidate knowledge."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class PromotedClaim:
    subject: str
    relation: str
    object: str
    source_claims: tuple[str, ...]
    inference_type: str
    promoted_at: str

    @property
    def claim_key(self) -> str:
        return "|".join([self.subject, self.relation, self.object])


def _extract_source_claims(stable_claim: object) -> tuple[str, ...]:
    source_claims = getattr(stable_claim, "source_claims", None)
    if isinstance(source_claims, tuple):
        return source_claims
    if isinstance(source_claims, list):
        return tuple(str(item) for item in source_claims)
    derived_from = getattr(stable_claim, "derived_from", None)
    if isinstance(derived_from, tuple):
        return tuple(str(item) for item in derived_from)
    if isinstance(derived_from, str):
        return (derived_from,)
    return ()


def promote_stable_claims(stable_claims, threshold: int) -> list[PromotedClaim]:
    if threshold < 1:
        raise ValueError("threshold must be >= 1")
    promoted_at = datetime.now(timezone.utc).isoformat()
    promoted: list[PromotedClaim] = []
    for stable_claim in stable_claims:
        occurrences = int(getattr(stable_claim, "occurrences", 0))
        if occurrences < threshold:
            continue
        claim_key = str(getattr(stable_claim, "claim_key", ""))
        parts = claim_key.split("|", 2)
        if len(parts) != 3:
            continue
        promoted.append(
            PromotedClaim(
                subject=parts[0],
                relation=parts[1],
                object=parts[2],
                source_claims=_extract_source_claims(stable_claim),
                inference_type=str(getattr(stable_claim, "inference_type", "")),
                promoted_at=promoted_at,
            )
        )
    return sorted(promoted, key=lambda item: item.claim_key)
