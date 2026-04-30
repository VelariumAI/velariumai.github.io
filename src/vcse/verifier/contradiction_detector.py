"""Deterministic contradiction detector."""

from __future__ import annotations

from collections import defaultdict

from vcse.memory.constraints import Constraint
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.verifier.base import VerificationResult


class ContradictionDetector:
    """Detects equality and numeric constraint conflicts."""

    def evaluate(self, state: WorldStateMemory, transition: object | None = None) -> VerificationResult:
        reasons: list[str] = []
        affected: list[str] = []

        self._detect_equality_conflicts(state, reasons, affected)
        self._detect_numeric_constraint_conflicts(state, reasons, affected)

        if reasons:
            return VerificationResult.fail_result(
                status="CONTRADICTIONS_DETECTED",
                reasons=reasons,
                affected_elements=affected,
            )

        return VerificationResult.pass_result(
            status="NO_CONTRADICTIONS",
            reasons=["No contradictions detected"],
        )

    def _detect_equality_conflicts(
        self, state: WorldStateMemory, reasons: list[str], affected: list[str]
    ) -> None:
        equals_by_subject: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for claim in state.claims.values():
            if claim.relation == "equals" and claim.status in {
                TruthStatus.ASSERTED,
                TruthStatus.SUPPORTED,
            }:
                equals_by_subject[claim.subject].append((claim.id, claim.object))

        for subject, entries in equals_by_subject.items():
            seen: dict[str, str] = {}
            for claim_id, object_value in entries:
                for prior_value, prior_claim_id in seen.items():
                    if prior_value != object_value:
                        reason = f"{subject} equals both {prior_value} and {object_value}"
                        state.record_contradiction(
                            prior_claim_id,
                            reason,
                            related_element_ids=[claim_id],
                            severity="high",
                        )
                        reasons.append(reason)
                        affected.extend([prior_claim_id, claim_id])
                seen[object_value] = claim_id

    def _detect_numeric_constraint_conflicts(
        self, state: WorldStateMemory, reasons: list[str], affected: list[str]
    ) -> None:
        by_target: dict[str, list[tuple[str, Constraint]]] = defaultdict(list)
        for index, constraint in enumerate(state.constraints):
            if constraint.kind == "numeric":
                by_target[constraint.target].append((state.constraint_id_for_index(index), constraint))

        for constraints in by_target.values():
            for left_index, (left_id, left) in enumerate(constraints):
                for right_id, right in constraints[left_index + 1 :]:
                    reason = self._numeric_conflict_reason(left, right)
                    if reason is None:
                        continue
                    state.record_contradiction(
                        left_id,
                        reason,
                        related_element_ids=[right_id],
                        severity="unsat",
                    )
                    reasons.append(reason)
                    affected.extend([left_id, right_id])

    def _numeric_conflict_reason(self, left: Constraint, right: Constraint) -> str | None:
        ordered = (left, right)
        for lower, upper in (ordered, tuple(reversed(ordered))):
            if lower.operator in {">", ">="} and upper.operator in {"<", "<="}:
                lower_value = lower.value
                upper_value = upper.value
                if not isinstance(lower_value, int | float) or not isinstance(
                    upper_value, int | float
                ):
                    return None
                if lower_value > upper_value:
                    return self._format_conflict(lower, upper)
                if lower_value == upper_value and (
                    lower.operator == ">" or upper.operator == "<"
                ):
                    return self._format_conflict(lower, upper)
        return None

    def _format_conflict(self, left: Constraint, right: Constraint) -> str:
        return (
            f"{left.target} {left.operator} {left.value} conflicts with "
            f"{right.target} {right.operator} {right.value}"
        )
