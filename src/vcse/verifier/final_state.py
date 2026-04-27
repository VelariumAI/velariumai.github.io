"""Final-state evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from vcse.memory.world_state import TruthStatus, WorldStateMemory


class FinalStatus(str, Enum):
    VERIFIED = "VERIFIED"
    INCONCLUSIVE = "INCONCLUSIVE"
    CONTRADICTORY = "CONTRADICTORY"
    UNSATISFIABLE = "UNSATISFIABLE"


@dataclass
class FinalStateEvaluation:
    status: FinalStatus
    answer: str | None = None
    proof_trace: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    verifier_score: float = 0.0


class FinalStateEvaluator:
    """Decides final answer status from verified world state."""

    def __init__(self, verifier_threshold: float = 0.7) -> None:
        self.verifier_threshold = verifier_threshold

    def evaluate(self, state: WorldStateMemory, verifier_score: float = 1.0) -> FinalStateEvaluation:
        if any(state.contradictions.values()):
            return FinalStateEvaluation(
                status=FinalStatus.CONTRADICTORY,
                reasons=["Contradiction exists in world state"],
                verifier_score=verifier_score,
            )

        if not state.goals:
            return FinalStateEvaluation(
                status=FinalStatus.INCONCLUSIVE,
                reasons=["No active goal"],
                verifier_score=verifier_score,
            )

        goal = state.goals[0]
        claim = state.find_claim(goal.subject, goal.relation, goal.object)
        if claim is None:
            return FinalStateEvaluation(
                status=FinalStatus.INCONCLUSIVE,
                reasons=[f"Goal not satisfied: {goal.text}"],
                verifier_score=verifier_score,
            )

        path = state.dependency_path_for_claim(claim.id)
        if state.has_contradiction_on_path(path):
            return FinalStateEvaluation(
                status=FinalStatus.CONTRADICTORY,
                answer=claim.text,
                proof_trace=state.proof_trace_for_claim(claim.id),
                reasons=["Contradiction touches proof path"],
                verifier_score=verifier_score,
            )

        if verifier_score < self.verifier_threshold:
            return FinalStateEvaluation(
                status=FinalStatus.INCONCLUSIVE,
                answer=claim.text,
                proof_trace=state.proof_trace_for_claim(claim.id),
                reasons=["Verifier score below threshold"],
                verifier_score=verifier_score,
            )

        if claim.status not in {TruthStatus.ASSERTED, TruthStatus.SUPPORTED}:
            return FinalStateEvaluation(
                status=FinalStatus.INCONCLUSIVE,
                answer=claim.text,
                proof_trace=state.proof_trace_for_claim(claim.id),
                reasons=[f"Goal claim has non-final truth status: {claim.status.value}"],
                verifier_score=verifier_score,
            )

        proof_trace = state.proof_trace_for_claim(claim.id)
        if not proof_trace:
            return FinalStateEvaluation(
                status=FinalStatus.INCONCLUSIVE,
                answer=claim.text,
                reasons=["No proof trace available"],
                verifier_score=verifier_score,
            )

        return FinalStateEvaluation(
            status=FinalStatus.VERIFIED,
            answer=claim.text,
            proof_trace=proof_trace,
            reasons=["Goal satisfied with dependency trace"],
            verifier_score=verifier_score,
        )
