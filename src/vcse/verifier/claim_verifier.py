"""Claim verifier."""

from __future__ import annotations

from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.verifier.base import VerificationResult


class ClaimVerifier:
    """Validates typed claims and dependency support."""

    def evaluate(self, state: WorldStateMemory, transition: object | None = None) -> VerificationResult:
        reasons: list[str] = []
        affected: list[str] = []

        for claim in state.claims.values():
            if state.relation_schemas and state.get_relation_schema(claim.relation) is None:
                return VerificationResult.fail_result(
                    status="UNKNOWN_RELATION",
                    reasons=[f"Claim {claim.id} uses unknown relation {claim.relation}"],
                    affected_elements=[claim.id],
                )

            if claim.status == TruthStatus.SUPPORTED and not claim.dependencies:
                reasons.append(f"Supported claim {claim.id} has no dependencies")
                affected.append(claim.id)

        score = 0.75 if affected else 1.0
        return VerificationResult.pass_result(
            status="CLAIMS_VERIFIED",
            score=score,
            reasons=reasons or ["Claims are schema-valid"],
            affected_elements=affected,
        )
