"""Beam search over state transitions."""

from __future__ import annotations

from dataclasses import dataclass

from vcse.memory.world_state import WorldStateMemory
from vcse.proposer.base import BaseProposer
from vcse.search.node import SearchNode
from vcse.search.result import SearchResult, SearchStats
from vcse.verifier.final_state import FinalStateEvaluator, FinalStatus
from vcse.verifier.stack import VerifierStack


@dataclass(frozen=True)
class SearchConfig:
    max_depth: int = 6
    beam_width: int = 4
    max_nodes_expanded: int = 500
    verifier_score_threshold: float = 0.0
    goal_progress_weight: float = 2.0
    verifier_score_weight: float = 1.0
    contradiction_penalty: float = 5.0
    depth_penalty: float = 0.1
    uncertainty_penalty: float = 0.5

    def __post_init__(self) -> None:
        if self.max_depth < 0:
            raise ValueError("max_depth must be >= 0")
        if self.beam_width < 1:
            raise ValueError("beam_width must be >= 1")
        if self.max_nodes_expanded < 0:
            raise ValueError("max_nodes_expanded must be >= 0")


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
        config: SearchConfig | None = None,
    ) -> None:
        self.proposer = proposer
        self.verifier_stack = verifier_stack
        self.final_state_evaluator = final_state_evaluator
        self.config = config or SearchConfig(
            max_depth=max_depth,
            beam_width=beam_width,
            max_nodes_expanded=max_nodes_expanded,
        )
        self.max_depth = self.config.max_depth
        self.beam_width = self.config.beam_width
        self.max_nodes_expanded = self.config.max_nodes_expanded
        self.nodes_expanded = 0
        self.max_depth_reached = 0
        self.max_frontier_size = 0

    def run(self, initial_state: WorldStateMemory) -> SearchResult:
        self.nodes_expanded = 0
        self.max_depth_reached = 0
        self.max_frontier_size = 1
        initial_score = self._score(initial_state, 0, 1.0)
        root = SearchNode(state=initial_state.clone(), score=initial_score, depth=0)
        best = root
        frontier = [root]
        best_evaluation = self.final_state_evaluator.evaluate(root.state)

        while frontier and self.nodes_expanded < self.config.max_nodes_expanded:
            next_frontier: list[SearchNode] = []
            self.max_frontier_size = max(self.max_frontier_size, len(frontier))

            for node in frontier:
                stack_result = self.verifier_stack.evaluate(node.state)
                final = self.final_state_evaluator.evaluate(node.state, stack_result.score)
                node.terminal_status = final.status.value
                node.score = self._score(node.state, node.depth, stack_result.score)
                self.max_depth_reached = max(self.max_depth_reached, node.depth)

                if node.score > best.score or final.status == FinalStatus.VERIFIED:
                    best = node
                    best_evaluation = final
                if final.status == FinalStatus.VERIFIED:
                    return self._result(best, final)
                if final.status in {FinalStatus.CONTRADICTORY, FinalStatus.UNSATISFIABLE}:
                    continue
                if node.depth >= self.config.max_depth:
                    continue

                goal = node.state.goals[0] if node.state.goals else None
                for transition in self.proposer.propose(node.state, goal):
                    if self.nodes_expanded >= self.config.max_nodes_expanded:
                        break
                    self.nodes_expanded += 1
                    new_state, transition_result = transition.apply(node.state)
                    if not transition_result.passed:
                        continue

                    stack_result = self.verifier_stack.evaluate(new_state, transition)
                    child_depth = node.depth + 1
                    final = self.final_state_evaluator.evaluate(new_state, stack_result.score)
                    child_score = self._score(new_state, child_depth, stack_result.score)

                    if (
                        not stack_result.passed
                        or final.status in {FinalStatus.CONTRADICTORY, FinalStatus.UNSATISFIABLE}
                        or stack_result.score < self.config.verifier_score_threshold
                    ):
                        continue

                    child = SearchNode(
                        state=new_state,
                        transition_history=[*node.transition_history, transition],
                        score=child_score,
                        depth=child_depth,
                        terminal_status=final.status.value,
                    )
                    self.max_depth_reached = max(self.max_depth_reached, child.depth)
                    if final.status == FinalStatus.VERIFIED:
                        return self._result(child, final)
                    next_frontier.append(child)

            next_frontier.sort(key=lambda item: item.score, reverse=True)
            frontier = next_frontier[: self.config.beam_width]
            self.max_frontier_size = max(self.max_frontier_size, len(frontier))
            if frontier and frontier[0].score > best.score:
                best = frontier[0]
                stack_result = self.verifier_stack.evaluate(best.state)
                best_evaluation = self.final_state_evaluator.evaluate(best.state, stack_result.score)

        stack_result = self.verifier_stack.evaluate(best.state)
        best_evaluation = self.final_state_evaluator.evaluate(best.state, stack_result.score)
        best.terminal_status = best_evaluation.status.value
        return self._result(best, best_evaluation)

    def _score(self, state: WorldStateMemory, depth: int, verifier_score: float) -> float:
        goal_progress = 0.0
        if state.goals:
            goal = state.goals[0]
            if state.find_claim(goal.subject, goal.relation, goal.object) is not None:
                goal_progress = self.config.goal_progress_weight
            elif goal.relation == "satisfies" and goal.object == "constraints":
                if goal.subject in state.symbol_bindings:
                    goal_progress = self.config.goal_progress_weight
        contradiction_penalty = (
            self.config.contradiction_penalty if any(state.contradictions.values()) else 0.0
        )
        depth_penalty = self.config.depth_penalty * depth
        uncertainty_penalty = 0.0 if goal_progress else self.config.uncertainty_penalty
        return (
            goal_progress
            + (self.config.verifier_score_weight * verifier_score)
            - contradiction_penalty
            - depth_penalty
            - uncertainty_penalty
        )

    def _result(self, best: SearchNode, evaluation) -> SearchResult:
        return SearchResult(
            best_node=best,
            evaluation=evaluation,
            stats=SearchStats(
                nodes_expanded=self.nodes_expanded,
                max_depth_reached=self.max_depth_reached,
                terminal_status=evaluation.status.value,
                best_score=best.score,
                max_frontier_size=self.max_frontier_size,
            ),
        )
