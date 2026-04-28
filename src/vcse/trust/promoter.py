"""Trust promotion engine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vcse.ledger.events import LedgerEvent, new_event
from vcse.ledger.store import LedgerStore
from vcse.trust.conflict import detect_conflicts
from vcse.trust.policy import StalenessPolicy, TrustPolicy
from vcse.trust.scorer import SourceAuthorityRegistry
from vcse.trust.staleness import evaluate_staleness
from vcse.trust.tiers import validate_transition


@dataclass(frozen=True)
class ClaimCluster:
    normalized_claim_key: str
    claims: list[dict[str, Any]]
    sources: list[str]
    support_count: int
    conflict_count: int
    highest_trust_source: str
    latest_timestamp: str
    candidate_tier: str


@dataclass
class TrustDecision:
    claim_id: str
    current_tier: str
    recommended_tier: str
    passed: bool
    reasons: list[str] = field(default_factory=list)
    blocking_issues: list[str] = field(default_factory=list)
    ledger_events: list[LedgerEvent] = field(default_factory=list)


@dataclass(frozen=True)
class TrustReport:
    decisions: list[TrustDecision]
    conflicts: list[dict[str, Any]]
    staleness: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisions": [
                {
                    "claim_id": item.claim_id,
                    "current_tier": item.current_tier,
                    "recommended_tier": item.recommended_tier,
                    "passed": item.passed,
                    "reasons": item.reasons,
                    "blocking_issues": item.blocking_issues,
                    "ledger_events": [event.to_dict() for event in item.ledger_events],
                }
                for item in self.decisions
            ],
            "conflicts": list(self.conflicts),
            "staleness": list(self.staleness),
        }


class ClaimClusterer:
    @staticmethod
    def canonical_key(claim: dict[str, Any]) -> str:
        qualifiers = claim.get("qualifiers", {}) or {}
        q = "|".join(f"{k}:{qualifiers[k]}" for k in sorted(qualifiers.keys()))
        return "|".join([
            str(claim.get("subject", "")).strip().lower(),
            str(claim.get("relation", "")).strip().lower(),
            str(claim.get("object", "")).strip().lower(),
            q,
        ])

    def cluster(self, claims: list[dict[str, Any]], registry: SourceAuthorityRegistry | None = None) -> list[ClaimCluster]:
        registry = registry or SourceAuthorityRegistry()
        groups: dict[str, list[dict[str, Any]]] = {}
        for claim in claims:
            groups.setdefault(self.canonical_key(claim), []).append(claim)
        output: list[ClaimCluster] = []
        for key, items in sorted(groups.items()):
            unique_sources = sorted({str(item.get("source_id") or item.get("source", "unknown")) for item in items})
            trust_sorted = sorted(unique_sources, key=lambda src: registry.score(src), reverse=True)
            latest_timestamp = max((str(item.get("created_at", "")) for item in items), default="")
            output.append(
                ClaimCluster(
                    normalized_claim_key=key,
                    claims=items,
                    sources=unique_sources,
                    support_count=len(unique_sources),
                    conflict_count=0,
                    highest_trust_source=trust_sorted[0] if trust_sorted else "unknown",
                    latest_timestamp=latest_timestamp,
                    candidate_tier="T0_CANDIDATE",
                )
            )
        return output


class CrossSourceValidator:
    def __init__(self, registry: SourceAuthorityRegistry | None = None) -> None:
        self.registry = registry or SourceAuthorityRegistry()

    def support_score(self, cluster: ClaimCluster) -> float:
        seen = set()
        score = 0.0
        for source in cluster.sources:
            if source in seen:
                continue
            seen.add(source)
            score += self.registry.score(source)
        return round(score, 4)


class TrustPromoter:
    def __init__(
        self,
        policy: TrustPolicy | None = None,
        source_registry: SourceAuthorityRegistry | None = None,
        staleness_policy: StalenessPolicy | None = None,
    ) -> None:
        self.policy = policy or TrustPolicy()
        self.source_registry = source_registry or SourceAuthorityRegistry()
        self.clusterer = ClaimClusterer()
        self.cross_validator = CrossSourceValidator(self.source_registry)
        self.staleness_policy = staleness_policy or StalenessPolicy()

    def evaluate_claim(self, claim: dict[str, Any], support_count: int = 1, conflict_count: int = 0) -> TrustDecision:
        claim_id = str(claim.get("claim_id", claim.get("id", "claim")))
        current_tier = str(claim.get("trust_tier", "T0_CANDIDATE"))
        reasons: list[str] = []
        blockers: list[str] = []
        target = current_tier

        has_provenance = bool(claim.get("provenance") or claim.get("source_id") or claim.get("source"))
        if current_tier == "T0_CANDIDATE" and has_provenance:
            target = "T1_PROVENANCED"
            reasons.append("provenance present")
        elif current_tier == "T0_CANDIDATE":
            blockers.append("missing provenance")

        src = str(claim.get("source_id") or claim.get("source", "unknown"))
        src_score = self.source_registry.score(src)
        if target == "T1_PROVENANCED" and src_score >= self.policy.source_trust_threshold:
            target = "T2_SOURCE_TRUSTED"
            reasons.append(f"source trust >= threshold ({src_score})")
        elif target == "T1_PROVENANCED":
            blockers.append("source trust below threshold")

        if target == "T2_SOURCE_TRUSTED":
            min_sources = self.policy.min_independent_sources
            if self.policy.allow_single_authoritative_source and src_score >= 0.9:
                min_sources = 1
            if support_count >= min_sources and conflict_count == 0:
                target = "T3_CROSS_SUPPORTED"
                reasons.append("cross-source support satisfied")
            else:
                blockers.append("insufficient independent source support or conflicts present")

        if target == "T3_CROSS_SUPPORTED":
            if self.policy.require_verifier_consistency:
                target = "T4_VERIFIER_CONSISTENT"
                reasons.append("verifier consistency requirement assumed pass")
            else:
                target = "T4_VERIFIER_CONSISTENT"

        if target == "T4_VERIFIER_CONSISTENT":
            if self.policy.require_gauntlet_pass:
                blockers.append("gauntlet confirmation required for certification")
            else:
                target = "T5_CERTIFIED"
                reasons.append("certification policy allows auto-promote")

        if conflict_count > 0:
            target = "T7_CONFLICTED"
            reasons.append("conflicts detected")

        stale = evaluate_staleness(claim, self.staleness_policy)
        if stale.stale:
            blockers.append(f"stale claim (age={stale.age_days}, freshness={stale.freshness_days})")

        if target != current_tier:
            _validate_transition_path(current_tier, target)
        events = [
            new_event(
                event_type="TRUST_PROMOTED",
                claim_id=claim_id,
                payload={
                    "current_tier": current_tier,
                    "recommended_tier": target,
                    "reasons": reasons,
                    "blocking_issues": blockers,
                },
            )
        ]
        return TrustDecision(
            claim_id=claim_id,
            current_tier=current_tier,
            recommended_tier=target,
            passed=(len(blockers) == 0 and target in {"T4_VERIFIER_CONSISTENT", "T5_CERTIFIED"}),
            reasons=reasons,
            blocking_issues=blockers,
            ledger_events=events,
        )

    def evaluate_cluster(self, cluster: ClaimCluster) -> TrustDecision:
        sample = dict(cluster.claims[0]) if cluster.claims else {"claim_id": cluster.normalized_claim_key}
        return self.evaluate_claim(sample, support_count=cluster.support_count, conflict_count=cluster.conflict_count)

    def evaluate_claims(self, claims: list[dict[str, Any]]) -> TrustReport:
        clusters = self.clusterer.cluster(claims, self.source_registry)
        conflicts = [item.__dict__ for item in detect_conflicts(claims)]
        conflict_claim_ids = {cid for item in conflicts for cid in item.get("affected_claims", [])}
        decisions: list[TrustDecision] = []
        staleness_rows: list[dict[str, Any]] = []

        key_to_conflicts: dict[str, int] = {}
        for cluster in clusters:
            count = 0
            for claim in cluster.claims:
                if str(claim.get("claim_id", "")) in conflict_claim_ids:
                    count += 1
            key_to_conflicts[cluster.normalized_claim_key] = count

        for cluster in clusters:
            for claim in cluster.claims:
                cid = str(claim.get("claim_id", claim.get("id", "")))
                stale = evaluate_staleness(claim, self.staleness_policy)
                staleness_rows.append(
                    {
                        "claim_id": cid,
                        "stale": stale.stale,
                        "reason": stale.reason,
                        "age_days": stale.age_days,
                        "freshness_days": stale.freshness_days,
                    }
                )
                decision = self.evaluate_claim(
                    claim,
                    support_count=cluster.support_count,
                    conflict_count=key_to_conflicts.get(cluster.normalized_claim_key, 0),
                )
                decisions.append(decision)
        return TrustReport(decisions=decisions, conflicts=conflicts, staleness=staleness_rows)

    def promote(self, pack_path: str | Path) -> TrustReport:
        root = Path(pack_path)
        claims_path = root / "claims.jsonl"
        if not claims_path.exists():
            from vcse.trust.errors import TrustError

            raise TrustError("MISSING_CLAIMS", f"missing claims.jsonl in {root}")
        claims: list[dict[str, Any]] = []
        for idx, line in enumerate(claims_path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            payload.setdefault("claim_id", f"claim:{idx}")
            payload.setdefault("source_id", payload.get("provenance", {}).get("source_id", "unknown"))
            payload.setdefault("created_at", datetime.now(timezone.utc).isoformat())
            claims.append(payload)

        report = self.evaluate_claims(claims)

        trust_report_path = root / "trust_report.json"
        trust_report_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")
        conflicts_path = root / "conflicts.jsonl"
        conflicts_path.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in report.conflicts))
        staleness_path = root / "staleness.jsonl"
        staleness_path.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in report.staleness))

        ledger = LedgerStore(root / "ledger_snapshot.json")
        for decision in report.decisions:
            for event in decision.ledger_events:
                ledger.append(event)

        return report


def _validate_transition_path(current_tier: str, target_tier: str) -> None:
    if target_tier in {"T7_CONFLICTED", "T6_DEPRECATED"}:
        validate_transition(current_tier, target_tier)
        return
    order = [
        "T0_CANDIDATE",
        "T1_PROVENANCED",
        "T2_SOURCE_TRUSTED",
        "T3_CROSS_SUPPORTED",
        "T4_VERIFIER_CONSISTENT",
        "T5_CERTIFIED",
    ]
    start_idx = order.index(current_tier)
    target_idx = order.index(target_tier)
    for idx in range(start_idx, target_idx):
        validate_transition(order[idx], order[idx + 1])
