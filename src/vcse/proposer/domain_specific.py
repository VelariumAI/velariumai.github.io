"""Domain-specific symbolic proposal rules."""

from __future__ import annotations

from vcse.memory.constraints import Constraint
from vcse.memory.world_state import Goal, TruthStatus, WorldStateMemory
from vcse.transitions.actions import ADD_CLAIM, ADD_EVIDENCE, BIND_SYMBOL, RECORD_CONTRADICTION
from vcse.transitions.state_transition import Transition
from vcse.verifier.constraint_verifier import compare_numeric


class DomainSpecificProposer:
    """Deterministic rules for arithmetic, symbolic logic, and planning hooks."""

    def __init__(self, max_proposals: int = 32) -> None:
        self.max_proposals = max_proposals

    def propose(self, memory: WorldStateMemory, goal: Goal | None = None) -> list[Transition]:
        proposals: list[Transition] = []
        proposals.extend(self._propose_arithmetic(memory))
        proposals.extend(self._propose_symbolic_logic(memory))
        proposals.extend(self.propose_planning(memory, goal))
        return proposals[: self.max_proposals]

    def propose_planning(
        self, memory: WorldStateMemory, goal: Goal | None = None
    ) -> list[Transition]:
        return []

    def _propose_arithmetic(self, memory: WorldStateMemory) -> list[Transition]:
        proposals: list[Transition] = []
        for claim in memory.claims.values():
            if claim.relation != "equals" or claim.status not in {
                TruthStatus.ASSERTED,
                TruthStatus.SUPPORTED,
            }:
                continue
            numeric_value = self._parse_number(claim.object)
            if numeric_value is None or claim.subject in memory.symbol_bindings:
                continue
            proposals.append(
                Transition(
                    type=BIND_SYMBOL,
                    args={"name": claim.subject, "value": numeric_value},
                    description=f"Bind numeric equality {claim.text}",
                    expected_effect="Numeric symbol binding is stored",
                    source="domain_arithmetic",
                )
            )

        for index, constraint in enumerate(memory.constraints):
            if constraint.kind != "numeric" or constraint.target not in memory.symbol_bindings:
                continue
            target_value = memory.symbol_bindings[constraint.target]
            constraint_id = memory.constraint_id_for_index(index)
            if not isinstance(target_value, int | float) or not isinstance(
                constraint.value, int | float
            ):
                continue
            if compare_numeric(target_value, constraint.operator, constraint.value):
                proposals.append(
                    Transition(
                        type=ADD_EVIDENCE,
                        args={
                            "target_id": constraint_id,
                            "content": (
                                f"{constraint.target}={target_value} satisfies "
                                f"{self._constraint_text(constraint)}"
                            ),
                            "source": "domain_arithmetic",
                        },
                        description=f"Attach arithmetic support for {constraint_id}",
                        expected_effect="Constraint satisfaction evidence is stored",
                        source="domain_arithmetic",
                    )
                )
            else:
                proposals.append(
                    Transition(
                        type=RECORD_CONTRADICTION,
                        args={
                            "element_id": constraint_id,
                            "reason": (
                                f"{constraint.target}={target_value} violates "
                                f"{self._constraint_text(constraint)}"
                            ),
                            "related_element_ids": [f"symbol:{constraint.target}"],
                            "severity": "unsat",
                        },
                        description=f"Record arithmetic conflict for {constraint_id}",
                        expected_effect="Constraint conflict is indexed",
                        source="domain_arithmetic",
                    )
                )
        return proposals

    def _propose_symbolic_logic(self, memory: WorldStateMemory) -> list[Transition]:
        proposals: list[Transition] = []
        true_claims = {
            claim.subject: claim
            for claim in memory.claims.values()
            if claim.relation == "is_true"
            and claim.status in {TruthStatus.ASSERTED, TruthStatus.SUPPORTED}
        }
        for implication in memory.claims.values():
            if implication.relation != "implies":
                continue
            premise = true_claims.get(implication.subject)
            if premise is None:
                continue
            if memory.find_claim(implication.object, "is_true", "true") is not None:
                continue
            proposals.append(
                Transition(
                    type=ADD_CLAIM,
                    args={
                        "subject": implication.object,
                        "relation": "is_true",
                        "object": "true",
                        "status": TruthStatus.SUPPORTED,
                        "dependencies": [premise.id, implication.id],
                    },
                    description=f"Apply implication {implication.text}",
                    expected_effect="Adds supported symbolic conclusion",
                    source="domain_logic",
                )
            )
        return proposals

    def _parse_number(self, value: str) -> int | float | None:
        try:
            number = float(value)
        except ValueError:
            return None
        if number.is_integer():
            return int(number)
        return number

    def _constraint_text(self, constraint: Constraint) -> str:
        return f"{constraint.target} {constraint.operator} {constraint.value}"
