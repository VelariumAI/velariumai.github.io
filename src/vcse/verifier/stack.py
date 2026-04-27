"""Verifier stack."""

from __future__ import annotations

from dataclasses import dataclass

from vcse.memory.world_state import WorldStateMemory
from vcse.verifier.base import VerificationResult, Verifier
from vcse.verifier.claim_verifier import ClaimVerifier


@dataclass
class VerifierStackResult:
    passed: bool
    score: float
    status: str
    reasons: list[str]
    affected_elements: list[str]
    results: list[VerificationResult]


class VerifierStack:
    def __init__(self, verifiers: list[Verifier]) -> None:
        self.verifiers = verifiers

    @classmethod
    def default(cls) -> "VerifierStack":
        return cls([ClaimVerifier()])

    def evaluate(
        self, state: WorldStateMemory, transition: object | None = None
    ) -> VerifierStackResult:
        results = [verifier.evaluate(state, transition) for verifier in self.verifiers]
        passed = all(result.passed for result in results)
        score = sum(result.score for result in results) / len(results) if results else 1.0
        reasons = [reason for result in results for reason in result.reasons]
        affected = [item for result in results for item in result.affected_elements]
        status = "VERIFIER_STACK_PASSED" if passed else "VERIFIER_STACK_FAILED"
        return VerifierStackResult(
            passed=passed,
            score=score,
            status=status,
            reasons=reasons,
            affected_elements=affected,
            results=results,
        )
