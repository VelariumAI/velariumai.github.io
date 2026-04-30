"""Knowledge pipeline metrics."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KnowledgeMetrics:
    claims_extracted: int = 0
    valid_claims: int = 0
    invalid_claims_rejected: int = 0
    duplicate_claims: int = 0
    conflicts_detected: int = 0
    sources_processed: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "claims_extracted": self.claims_extracted,
            "valid_claims": self.valid_claims,
            "invalid_claims_rejected": self.invalid_claims_rejected,
            "duplicate_claims": self.duplicate_claims,
            "conflicts_detected": self.conflicts_detected,
            "sources_processed": self.sources_processed,
        }
