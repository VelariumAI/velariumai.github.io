"""Beam search over state transitions."""

from __future__ import annotations

from vcse.memory.world_state import WorldStateMemory
from vcse.proposer.base import BaseProposer
from vcse.search.node import SearchNode
from vcse.verifier.final_state import FinalStateEvaluator, FinalStatus
from vcse.verifier.stack import VerifierStack


class BeamSearch:
    """Bounded search over explicit state transitions."""

    def __init__(
        self,
        proposer: BaseProposer,
        verifier_stack: VerifierStack,
        final_state_evaluator: FinalStateEvaluator,
        max_depth: int = 6,
        beam_width: int = 4,
        max_nodes_expanded: int = 500,
    ) -> None:
        self.proposer = proposer
        self.verifier_stack = verifier_stack
        self.final_state_evaluator = final_state_evaluator
        self.max_depth = max_depth
        self.beam_width = beam_width
        self.max_nodes_expanded = max_nodes_expanded
        self.nodes_expanded = 0

    def run(self, initial_state: WorldStateMemory) -> SearchNode:
        initial_score = self._score(initial_state, 0, 1.0)
        root = SearchNode(state=initial_state.clone(), score=initial_score, depth=0)
        best = root
        frontier = [root]

        while frontier and self.nodes_expanded < self.max_nodes_expanded:
            next_frontier: list[SearchNode] = []

            for node in frontier:
                stack_result = self.verifier_stack.evaluate(node.state)
                final = self.final_state_evaluator.evaluate(node.state, stack_result.score)
                node.terminal_status = final.status.value
                node.score = self._score(node.state, node.depth, stack_result.score)

                if node.score > best.score or final.status == FinalStatus.VERIFIED:
                    best = node
                if final.status == FinalStatus.VERIFIED:
                    return node
                if node.depth >= self.max_depth:
                    continue

                goal = node.state.goals[0] if node.state.goals else None
                for transition in self.proposer.propose(node.state, goal):
                    if self.nodes_expanded >= self.max_nodes_expanded:
                        break
                    self.nodes_expanded += 1
                    new_state, transition_result = transition.apply(node.state)
                    if not transition_result.passed:
                        continue

                    stack_result = self.verifier_stack.evaluate(new_state, transition)
                    if not stack_result.passed:
                        continue

                    child = SearchNode(
                        state=new_state,
                        transition_history=[*node.transition_history, transition],
                        score=self._score(new_state, node.depth + 1, stack_result.score),
                        depth=node.depth + 1,
                    )
                    final = self.final_state_evaluator.evaluate(child.state, stack_result.score)
                    child.terminal_status = final.status.value
                    if final.status == FinalStatus.VERIFIED:
                        return child
                    next_frontier.append(child)

            next_frontier.sort(key=lambda item: item.score, reverse=True)
            frontier = next_frontier[: self.beam_width]
            if frontier and frontier[0].score > best.score:
                best = frontier[0]

        return best

    def _score(self, state: WorldStateMemory, depth: int, verifier_score: float) -> float:
        goal_progress = 0.0
        if state.goals:
            goal = state.goals[0]
            if state.find_claim(goal.subject, goal.relation, goal.object) is not None:
                goal_progress = 2.0
        contradiction_penalty = 5.0 if any(state.contradictions.values()) else 0.0
        depth_penalty = 0.1 * depth
        uncertainty_penalty = 0.0 if goal_progress else 0.5
        return goal_progress + verifier_score - contradiction_penalty - depth_penalty - uncertainty_penalty
