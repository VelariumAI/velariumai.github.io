"""Claim lifecycle tracking helpers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ClaimLifecycle:
    claim_id: str
    current_tier: str = "T0_CANDIDATE"
    flags: set[str] = field(default_factory=set)
    created_at: str = ""
    certified_at: str | None = None
    supersedes: str | None = None

    def with_flag(self, flag: str) -> "ClaimLifecycle":
        clone = ClaimLifecycle(
            claim_id=self.claim_id,
            current_tier=self.current_tier,
            flags=set(self.flags),
            created_at=self.created_at,
            certified_at=self.certified_at,
            supersedes=self.supersedes,
        )
        clone.flags.add(flag)
        return clone
