"""Rule-based proposer."""

from __future__ import annotations

from collections import defaultdict

from vcse.memory.world_state import Goal, TruthStatus, WorldStateMemory
from vcse.transitions.actions import ADD_CLAIM, RECORD_CONTRADICTION
from vcse.transitions.state_transition import Transition


class RuleBasedProposer:
    """Deterministic proposal module for simple symbolic closures."""

    def __init__(self, max_proposals: int = 32, external_rules: list[object] | None = None) -> None:
        self.max_proposals = max_proposals
        self.external_rules = list(external_rules or [])

    def propose(self, memory: WorldStateMemory, goal: Goal | None = None) -> list[Transition]:
        proposals: list[Transition] = []
        claims = list(memory.claims.values())
        proposals.extend(self._propose_transitive_closure(memory, claims))
        proposals.extend(self._propose_equality_propagation(memory, claims))
        proposals.extend(self._propose_contradiction_candidates(memory, claims))
        proposals.extend(self._propose_external_rules(memory, claims))
        return self._goal_first(self._limit(proposals), goal)

    def _propose_transitive_closure(self, memory: WorldStateMemory, claims) -> list[Transition]:
        proposals: list[Transition] = []
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
                        type=ADD_CLAIM,
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
                    return proposals

        return proposals

    def _propose_equality_propagation(self, memory: WorldStateMemory, claims) -> list[Transition]:
        proposals: list[Transition] = []
        equalities = [
            claim
            for claim in claims
            if claim.relation == "equals"
            and claim.status in {TruthStatus.ASSERTED, TruthStatus.SUPPORTED}
        ]
        for equality in equalities:
            for claim in claims:
                if claim.id == equality.id or claim.relation == "equals":
                    continue
                if claim.subject == equality.object:
                    if memory.find_claim(equality.subject, claim.relation, claim.object) is None:
                        proposals.append(
                            Transition(
                                type=ADD_CLAIM,
                                args={
                                    "subject": equality.subject,
                                    "relation": claim.relation,
                                    "object": claim.object,
                                    "status": TruthStatus.SUPPORTED,
                                    "dependencies": [equality.id, claim.id],
                                },
                                description=(
                                    f"Propagate equality from {equality.text} through {claim.text}"
                                ),
                                expected_effect="Adds equality-propagated supported claim",
                                source="rule_based",
                            )
                        )
                if claim.object == equality.subject:
                    if memory.find_claim(claim.subject, claim.relation, equality.object) is None:
                        proposals.append(
                            Transition(
                                type=ADD_CLAIM,
                                args={
                                    "subject": claim.subject,
                                    "relation": claim.relation,
                                    "object": equality.object,
                                    "status": TruthStatus.SUPPORTED,
                                    "dependencies": [claim.id, equality.id],
                                },
                                description=(
                                    f"Propagate equality from {equality.text} through {claim.text}"
                                ),
                                expected_effect="Adds equality-propagated supported claim",
                                source="rule_based",
                            )
                        )
        return proposals

    def _propose_contradiction_candidates(self, memory: WorldStateMemory, claims) -> list[Transition]:
        proposals: list[Transition] = []
        equals_by_subject: dict[str, list] = defaultdict(list)
        for claim in claims:
            if claim.relation == "equals" and claim.status in {
                TruthStatus.ASSERTED,
                TruthStatus.SUPPORTED,
            }:
                equals_by_subject[claim.subject].append(claim)

        for subject, entries in equals_by_subject.items():
            for index, left in enumerate(entries):
                for right in entries[index + 1 :]:
                    if left.object == right.object:
                        continue
                    if memory.get_contradictions_for(left.id):
                        continue
                    proposals.append(
                        Transition(
                            type=RECORD_CONTRADICTION,
                            args={
                                "element_id": left.id,
                                "reason": f"{subject} equals both {left.object} and {right.object}",
                                "related_element_ids": [right.id],
                                "severity": "high",
                            },
                            description=f"Record conflicting equality for {subject}",
                            expected_effect="Contradiction candidate is indexed",
                            source="rule_based",
                        )
                    )
        return proposals

    def _limit(self, proposals: list[Transition]) -> list[Transition]:
        return proposals[: self.max_proposals]

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

    def _propose_external_rules(self, memory: WorldStateMemory, claims) -> list[Transition]:
        proposals: list[Transition] = []
        for rule in self.external_rules:
            when = getattr(rule, "when", None)
            then = getattr(rule, "then", None)
            if not isinstance(when, list) or not isinstance(then, dict):
                continue
            bindings, dependencies = self._match_rule(when, claims)
            if bindings is None:
                continue
            action = str(then.get("action", ""))
            if action != ADD_CLAIM:
                continue
            subject = self._bind(str(then.get("subject", "")), bindings)
            relation = self._bind(str(then.get("relation", "")), bindings)
            obj = self._bind(str(then.get("object", "")), bindings)
            if not subject or not relation or not obj:
                continue
            if memory.find_claim(subject, relation, obj) is not None:
                continue
            proposals.append(
                Transition(
                    type=ADD_CLAIM,
                    args={
                        "subject": subject,
                        "relation": relation,
                        "object": obj,
                        "status": TruthStatus.SUPPORTED,
                        "dependencies": dependencies,
                    },
                    description=f"DSL rule infer {subject} {relation} {obj}",
                    expected_effect="Adds DSL-supported claim",
                    source="dsl_proposer",
                )
            )
        return proposals

    def _match_rule(self, conditions: list[dict[str, str]], claims) -> tuple[dict[str, str] | None, list[str]]:
        bindings: dict[str, str] = {}
        dependencies: list[str] = []
        for condition in conditions:
            matched_claim = None
            for claim in claims:
                local_bindings = dict(bindings)
                if not self._match_value(condition.get("subject", ""), claim.subject, local_bindings):
                    continue
                if not self._match_value(condition.get("relation", ""), claim.relation, local_bindings):
                    continue
                if not self._match_value(condition.get("object", ""), claim.object, local_bindings):
                    continue
                matched_claim = claim
                bindings = local_bindings
                break
            if matched_claim is None:
                return None, []
            dependencies.append(matched_claim.id)
        return bindings, dependencies

    def _match_value(self, pattern: str, actual: str, bindings: dict[str, str]) -> bool:
        token = pattern.strip()
        if token.startswith("{") and token.endswith("}"):
            key = token[1:-1]
            existing = bindings.get(key)
            if existing is None:
                bindings[key] = actual
                return True
            return existing == actual
        return token == actual

    def _bind(self, template: str, bindings: dict[str, str]) -> str:
        value = template
        for key, mapped in bindings.items():
            value = value.replace("{" + key + "}", mapped)
        return value
