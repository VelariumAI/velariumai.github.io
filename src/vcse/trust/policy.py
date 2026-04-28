"""Trust policy model and loading."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TrustPolicy:
    source_trust_threshold: float = 0.7
    min_independent_sources: int = 2
    require_verifier_consistency: bool = True
    require_gauntlet_pass: bool = True
    allow_single_authoritative_source: bool = False
    high_risk_domain: bool = False


@dataclass(frozen=True)
class StalenessPolicy:
    domain: str = "general"
    freshness_days: int = 365
    relation_overrides: dict[str, int] | None = None

    def freshness_for(self, relation: str) -> int:
        if self.relation_overrides and relation in self.relation_overrides:
            return int(self.relation_overrides[relation])
        return int(self.freshness_days)


def load_policy(path: str | Path | None) -> TrustPolicy:
    if path is None:
        return TrustPolicy()
    payload = json.loads(Path(path).read_text())
    return TrustPolicy(
        source_trust_threshold=float(payload.get("source_trust_threshold", 0.7)),
        min_independent_sources=int(payload.get("min_independent_sources", 2)),
        require_verifier_consistency=bool(payload.get("require_verifier_consistency", True)),
        require_gauntlet_pass=bool(payload.get("require_gauntlet_pass", True)),
        allow_single_authoritative_source=bool(payload.get("allow_single_authoritative_source", False)),
        high_risk_domain=bool(payload.get("high_risk_domain", False)),
    )
