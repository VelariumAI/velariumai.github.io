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
        contradiction_reasons = self._contradiction_reasons(state)
        has_unsat = self._has_unsat_contradiction(state)
        if not state.goals:
            if has_unsat:
                return FinalStateEvaluation(
                    status=FinalStatus.UNSATISFIABLE,
                    reasons=contradiction_reasons or ["Unsatisfiable state"],
                    verifier_score=verifier_score,
                )
            if contradiction_reasons:
                return FinalStateEvaluation(
                    status=FinalStatus.CONTRADICTORY,
                    reasons=contradiction_reasons,
                    verifier_score=verifier_score,
                )
            return FinalStateEvaluation(
                status=FinalStatus.INCONCLUSIVE,
                reasons=["No active goal"],
                verifier_score=verifier_score,
            )

        goal = state.goals[0]

        constraint_answer = self._evaluate_constraint_goal(
            state, verifier_score, contradiction_reasons, has_unsat
        )
        if constraint_answer is not None:
            return constraint_answer

        claim = state.find_claim(goal.subject, goal.relation, goal.object)
        if claim is None:
            if has_unsat:
                return FinalStateEvaluation(
                    status=FinalStatus.UNSATISFIABLE,
                    reasons=contradiction_reasons or ["Unsatisfiable state"],
                    verifier_score=verifier_score,
                )
            if contradiction_reasons:
                return FinalStateEvaluation(
                    status=FinalStatus.CONTRADICTORY,
                    reasons=contradiction_reasons,
                    verifier_score=verifier_score,
                )
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

        if has_unsat:
            return FinalStateEvaluation(
                status=FinalStatus.UNSATISFIABLE,
                answer=claim.text,
                proof_trace=state.proof_trace_for_claim(claim.id),
                reasons=contradiction_reasons or ["Unsatisfiable state"],
                verifier_score=verifier_score,
            )

        if contradiction_reasons:
            return FinalStateEvaluation(
                status=FinalStatus.CONTRADICTORY,
                answer=claim.text,
                proof_trace=state.proof_trace_for_claim(claim.id),
                reasons=contradiction_reasons,
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

    def _evaluate_constraint_goal(
        self,
        state: WorldStateMemory,
        verifier_score: float,
        contradiction_reasons: list[str],
        has_unsat: bool,
    ) -> FinalStateEvaluation | None:
        if not state.goals:
            return None
        goal = state.goals[0]
        if goal.relation != "satisfies" or goal.object != "constraints":
            return None

        if has_unsat:
            return FinalStateEvaluation(
                status=FinalStatus.UNSATISFIABLE,
                answer=goal.text,
                reasons=contradiction_reasons or ["Unsatisfiable constraints"],
                verifier_score=verifier_score,
            )
        if contradiction_reasons:
            return FinalStateEvaluation(
                status=FinalStatus.CONTRADICTORY,
                answer=goal.text,
                reasons=contradiction_reasons,
                verifier_score=verifier_score,
            )
        if verifier_score < self.verifier_threshold:
            return FinalStateEvaluation(
                status=FinalStatus.INCONCLUSIVE,
                answer=goal.text,
                reasons=["Verifier score below threshold"],
                verifier_score=verifier_score,
            )
        target_constraints = [
            constraint for constraint in state.constraints if constraint.target == goal.subject
        ]
        if goal.subject not in state.symbol_bindings or not target_constraints:
            return FinalStateEvaluation(
                status=FinalStatus.INCONCLUSIVE,
                answer=goal.text,
                reasons=[f"Goal not satisfied: {goal.text}"],
                verifier_score=verifier_score,
            )
        return FinalStateEvaluation(
            status=FinalStatus.VERIFIED,
            answer=goal.text,
            proof_trace=[goal.text],
            reasons=["Constraint goal satisfied"],
            verifier_score=verifier_score,
        )

    def _contradiction_reasons(self, state: WorldStateMemory) -> list[str]:
        seen: set[str] = set()
        reasons: list[str] = []
        for contradictions in state.contradictions.values():
            for contradiction in contradictions:
                if contradiction.reason in seen:
                    continue
                seen.add(contradiction.reason)
                reasons.append(contradiction.reason)
        return reasons

    def _has_unsat_contradiction(self, state: WorldStateMemory) -> bool:
        return any(
            contradiction.severity == "unsat"
            for contradictions in state.contradictions.values()
            for contradiction in contradictions
        )
