"""Solver-backed symbolic proposal rules."""

from __future__ import annotations

from vcse.memory.constraints import Constraint
from vcse.memory.world_state import Goal, WorldStateMemory
from vcse.transitions.actions import ADD_EVIDENCE, RECORD_CONTRADICTION
from vcse.transitions.state_transition import Transition
from vcse.verifier.base import VerificationResult


class SolverBackedProposer:
    """Optional SMT-backed proposer that remains CPU-only."""

    def __init__(self, max_proposals: int = 32) -> None:
        self.max_proposals = max_proposals
        self._last_status = self._detect_support()

    def support_status(self) -> VerificationResult:
        return self._last_status

    def propose(self, memory: WorldStateMemory, goal: Goal | None = None) -> list[Transition]:
        self._last_status = self._detect_support()
        if not self._last_status.passed:
            return []

        try:
            import z3  # type: ignore[import-not-found]
        except ImportError:
            self._last_status = self._unavailable()
            return []

        proposals: list[Transition] = []
        by_target: dict[str, list[tuple[str, Constraint]]] = {}
        for index, constraint in enumerate(memory.constraints):
            if constraint.kind == "numeric" and isinstance(constraint.value, int | float):
                by_target.setdefault(constraint.target, []).append(
                    (memory.constraint_id_for_index(index), constraint)
                )

        for target, constraints in by_target.items():
            solver = z3.Solver()
            symbol = z3.Real(target)
            for _, constraint in constraints:
                solver.add(self._z3_expr(symbol, constraint))
            check_result = solver.check()
            target_ids = [constraint_id for constraint_id, _ in constraints]
            if check_result == z3.unsat:
                proposals.append(
                    Transition(
                        type=RECORD_CONTRADICTION,
                        args={
                            "element_id": target_ids[0],
                            "reason": f"Constraints for {target} are unsatisfiable",
                            "related_element_ids": target_ids[1:],
                            "severity": "unsat",
                        },
                        description=f"Record solver conflict for {target}",
                        expected_effect="Solver conflict is indexed",
                        source="solver_backed",
                    )
                )
            elif check_result == z3.sat:
                proposals.append(
                    Transition(
                        type=ADD_EVIDENCE,
                        args={
                            "target_id": target_ids[0],
                            "content": f"Constraints for {target} are satisfiable",
                            "source": "solver_backed",
                        },
                        description=f"Attach solver support for {target}",
                        expected_effect="Solver satisfiability evidence is stored",
                        source="solver_backed",
                    )
                )
            if len(proposals) >= self.max_proposals:
                break

        return proposals[: self.max_proposals]

    def _detect_support(self) -> VerificationResult:
        try:
            import z3  # noqa: F401  # type: ignore[import-not-found]
        except ImportError:
            return self._unavailable()
        return VerificationResult.pass_result(
            status="SOLVER_AVAILABLE",
            reasons=["z3 is available"],
        )

    def _unavailable(self) -> VerificationResult:
        return VerificationResult.fail_result(
            status="SOLVER_UNAVAILABLE",
            reasons=["z3 is unavailable; solver-backed proposals skipped"],
        )

    def _z3_expr(self, symbol, constraint: Constraint):
        if constraint.operator == ">":
            return symbol > constraint.value
        if constraint.operator == ">=":
            return symbol >= constraint.value
        if constraint.operator == "<":
            return symbol < constraint.value
        if constraint.operator == "<=":
            return symbol <= constraint.value
        if constraint.operator == "==":
            return symbol == constraint.value
        if constraint.operator == "!=":
            return symbol != constraint.value
        raise ValueError(f"Unsupported operator: {constraint.operator}")
