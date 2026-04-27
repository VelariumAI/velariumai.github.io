"""Rule-based proposer."""

from __future__ import annotations

from vcse.memory.world_state import Goal, TruthStatus, WorldStateMemory
from vcse.transitions.state_transition import Transition


class RuleBasedProposer:
    """Deterministic proposal module for simple symbolic closures."""

    def __init__(self, max_proposals: int = 32) -> None:
        self.max_proposals = max_proposals

    def propose(self, memory: WorldStateMemory, goal: Goal | None = None) -> list[Transition]:
        proposals: list[Transition] = []
        claims = list(memory.claims.values())

        for left in claims:
            schema = memory.get_relation_schema(left.relation)
            if schema is None or not schema.transitive:
                continue

            for right in claims:
                if left.relation != right.relation or left.object != right.subject:
                    continue

                if memory.find_claim(left.subject, left.relation, right.object) is not None:
                    continue

                proposals.append(
                    Transition(
                        type="AddClaim",
                        args={
                            "subject": left.subject,
                            "relation": left.relation,
                            "object": right.object,
                            "status": TruthStatus.SUPPORTED,
                            "dependencies": [left.id, right.id],
                        },
                        description=f"Infer {left.subject} {left.relation} {right.object}",
                        expected_effect="Adds transitive supported claim",
                        source="rule_based",
                    )
                )

                if len(proposals) >= self.max_proposals:
                    return self._goal_first(proposals, goal)

        return self._goal_first(proposals, goal)

    def _goal_first(self, proposals: list[Transition], goal: Goal | None) -> list[Transition]:
        if goal is None:
            return proposals
        return sorted(
            proposals,
            key=lambda item: (
                item.args.get("subject") != goal.subject
                or item.args.get("relation") != goal.relation
                or item.args.get("object") != goal.object
            ),
        )
