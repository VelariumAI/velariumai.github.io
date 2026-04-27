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
                return VerificationResult.fail_result(
                    status="UNSUPPORTED_CLAIM",
                    reasons=[f"Supported claim {claim.id} has no dependencies"],
                    affected_elements=[claim.id],
                )

            if claim.status == TruthStatus.SUPPORTED and claim.dependencies:
                support_result = self._verify_dependency_support(state, claim.id)
                if not support_result.passed:
                    return support_result
                reasons.extend(support_result.reasons)
                affected.extend(support_result.affected_elements)

        score = 0.75 if affected else 1.0
        return VerificationResult.pass_result(
            status="CLAIMS_VERIFIED",
            score=1.0 if affected else score,
            reasons=reasons or ["Claims are schema-valid"],
            affected_elements=affected,
        )

    def _verify_dependency_support(
        self, state: WorldStateMemory, claim_id: str
    ) -> VerificationResult:
        claim = state.get_claim(claim_id)
        if claim is None:
            return VerificationResult.fail_result(
                status="UNKNOWN_CLAIM",
                reasons=[f"Unknown claim {claim_id}"],
                affected_elements=[claim_id],
            )

        schema = state.get_relation_schema(claim.relation)
        if schema is not None and schema.transitive and len(claim.dependencies) == 2:
            left = state.get_claim(claim.dependencies[0])
            right = state.get_claim(claim.dependencies[1])
            if (
                left is not None
                and right is not None
                and left.relation == claim.relation
                and right.relation == claim.relation
                and left.subject == claim.subject
                and left.object == right.subject
                and right.object == claim.object
            ):
                return VerificationResult.pass_result(
                    status="CLAIM_SUPPORTED",
                    reasons=[f"Transitive support verified for {claim.text}"],
                    affected_elements=[claim.id],
                )

            return VerificationResult.fail_result(
                status="INVALID_SUPPORT",
                reasons=[f"Dependencies do not support {claim.text}"],
                affected_elements=[claim.id],
            )

        missing = [
            dependency_id
            for dependency_id in claim.dependencies
            if state.get_claim(dependency_id) is None
        ]
        if missing:
            return VerificationResult.fail_result(
                status="INVALID_SUPPORT",
                reasons=[f"Missing dependencies for {claim.text}: {', '.join(missing)}"],
                affected_elements=[claim.id, *missing],
            )

        return VerificationResult.pass_result(
            status="CLAIM_SUPPORTED",
            reasons=[f"Dependency support present for {claim.text}"],
            affected_elements=[claim.id],
        )
