"""Trust metrics."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrustMetrics:
    total_claims: int
    certified_claims: int
    conflicted_claims: int
    stale_claims: int
    cross_supported_claims: int

    def to_dict(self) -> dict[str, float | int]:
        total = self.total_claims if self.total_claims > 0 else 1
        return {
            "total_claims": self.total_claims,
            "certified_claims": self.certified_claims,
            "conflicted_claims": self.conflicted_claims,
            "stale_claims": self.stale_claims,
            "cross_supported_claims": self.cross_supported_claims,
            "certified_rate": self.certified_claims / total,
            "conflicted_rate": self.conflicted_claims / total,
            "stale_rate": self.stale_claims / total,
        }
