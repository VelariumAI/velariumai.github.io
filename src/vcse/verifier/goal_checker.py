"""Goal satisfaction verifier."""

from __future__ import annotations

from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.verifier.base import VerificationResult


class GoalSatisfactionChecker:
    """Checks goals without inventing new claims."""

    def evaluate(self, state: WorldStateMemory, transition: object | None = None) -> VerificationResult:
        if not state.goals:
            return VerificationResult.pass_result(
                status="NO_GOAL",
                score=0.8,
                reasons=["No active goal"],
            )

        satisfied: list[str] = []
        unmet: list[str] = []
        for goal in state.goals:
            if goal.relation == "satisfies" and goal.object == "constraints":
                if self._constraints_satisfied_for_target(state, goal.subject):
                    satisfied.append(goal.id)
                else:
                    unmet.append(goal.id)
                continue

            claim = state.find_claim(goal.subject, goal.relation, goal.object)
            if claim is not None and claim.status in {TruthStatus.ASSERTED, TruthStatus.SUPPORTED}:
                satisfied.append(goal.id)
            else:
                unmet.append(goal.id)

        if unmet and not satisfied:
            return VerificationResult.pass_result(
                status="GOAL_UNMET",
                score=0.4,
                reasons=[f"Goal not satisfied: {state.goals[0].text}"],
                affected_elements=unmet,
            )

        if unmet:
            return VerificationResult.pass_result(
                status="GOALS_PARTIALLY_SATISFIED",
                score=0.7,
                reasons=["Some goals are unsatisfied"],
                affected_elements=[*satisfied, *unmet],
            )

        return VerificationResult.pass_result(
            status="GOALS_SATISFIED",
            score=1.0,
            reasons=["Goals are satisfied"],
            affected_elements=satisfied,
        )

    def _constraints_satisfied_for_target(self, state: WorldStateMemory, target: str) -> bool:
        target_constraints = [
            constraint for constraint in state.constraints if constraint.target == target
        ]
        if not target_constraints:
            return False
        return not any(
            contradiction
            for index, constraint in enumerate(state.constraints)
            if constraint.target == target
            for contradiction in state.get_contradictions_for(state.constraint_id_for_index(index))
        )
