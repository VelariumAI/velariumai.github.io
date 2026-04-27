"""Structured constraint verifier."""

from __future__ import annotations

from typing import Any

from vcse.memory.constraints import Constraint
from vcse.memory.world_state import WorldStateMemory
from vcse.verifier.base import VerificationResult


def compare_numeric(left: float | int, operator: str, right: float | int) -> bool:
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right
    raise ValueError(f"Unsupported numeric operator: {operator}")


def format_value(value: Any) -> str:
    return str(value)


class ConstraintVerifier:
    """Evaluates structured numeric constraints against bound symbols."""

    def evaluate(self, state: WorldStateMemory, transition: object | None = None) -> VerificationResult:
        reasons: list[str] = []
        affected: list[str] = []

        for index, constraint in enumerate(state.constraints):
            constraint_id = state.constraint_id_for_index(index)
            if constraint.kind != "numeric":
                reasons.append(f"Skipped non-numeric constraint {constraint_id}")
                continue

            if constraint.target not in state.symbol_bindings:
                reasons.append(f"No binding for {constraint.target}; constraint pending")
                continue

            bound_value = state.symbol_bindings[constraint.target]
            if not isinstance(bound_value, int | float) or not isinstance(
                constraint.value, int | float
            ):
                return VerificationResult.fail_result(
                    status="CONSTRAINTS_VIOLATED",
                    reasons=[
                        f"{constraint.target} has non-numeric value for numeric constraint"
                    ],
                    affected_elements=[constraint_id],
                )

            if not compare_numeric(bound_value, constraint.operator, constraint.value):
                reason = (
                    f"{constraint.target}={format_value(bound_value)} violates "
                    f"{constraint.target} {constraint.operator} {format_value(constraint.value)}"
                )
                state.record_contradiction(
                    constraint_id,
                    reason,
                    related_element_ids=[f"symbol:{constraint.target}"],
                    severity="unsat",
                )
                reasons.append(reason)
                affected.append(constraint_id)

        if affected:
            return VerificationResult.fail_result(
                status="CONSTRAINTS_VIOLATED",
                reasons=reasons,
                affected_elements=affected,
            )

        return VerificationResult.pass_result(
            status="CONSTRAINTS_VERIFIED",
            reasons=reasons or ["Constraints are satisfied or pending"],
        )
