"""Beam search over state transitions."""

from __future__ import annotations

from dataclasses import dataclass

from vcse.memory.world_state import WorldStateMemory
from vcse.proposer.base import BaseProposer
from vcse.search.backend import SearchBackend
from vcse.search.node import SearchNode
from vcse.search.result import SearchResult, SearchStats
from vcse.ts3.signature import StateSignature
from vcse.ts3.symbolic_state import SymbolicState
from vcse.ts3.trajectory import Trajectory
from vcse.ts3.transient_analyzer import TransientAnalyzer
from vcse.verifier.final_state import FinalStateEvaluator, FinalStatus
from vcse.verifier.stack import VerifierStack
from vcse.perf import increment, stage


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
    enable_ts3: bool = False
    ts3_stagnation_penalty: float = 0.0
    search_backend: str = "beam"
    mcts_iterations: int = 100
    mcts_exploration_weight: float = 1.4
    mcts_max_depth: int = 8
    mcts_rollout_depth: int = 4

    def __post_init__(self) -> None:
        if self.max_depth < 0:
            raise ValueError("max_depth must be >= 0")
        if self.beam_width < 1:
            raise ValueError("beam_width must be >= 1")
        if self.max_nodes_expanded < 0:
            raise ValueError("max_nodes_expanded must be >= 0")


class BeamSearch(SearchBackend):
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
        self._ts3: TransientAnalyzer | None = None

    def run(self, initial_state: WorldStateMemory) -> SearchResult:
        with stage("search.beam"):
            self.nodes_expanded = 0
            self.max_depth_reached = 0
            self.max_frontier_size = 1
            self._ts3 = TransientAnalyzer() if self.config.enable_ts3 else None
            initial_score = self._score(initial_state, 0, 1.0)
            root_state = initial_state.clone()
            root_signature = self._signature_for(root_state)
            root = SearchNode(
                state=root_state,
                score=initial_score,
                depth=0,
                state_signature=root_signature,
                path_signatures=(root_signature,) if root_signature else tuple(),
            )
            best = root
            frontier = [root]
            best_evaluation = self.final_state_evaluator.evaluate(root.state)
            self._observe_ts3_state(root, best_evaluation.status.value, outgoing_transition_count=0)

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
                        self._observe_ts3_terminal(final.status.value)
                        continue
                    if node.depth >= self.config.max_depth:
                        self._observe_ts3_terminal(FinalStatus.INCONCLUSIVE.value)
                        continue

                    goal = node.state.goals[0] if node.state.goals else None
                    proposals = self.proposer.propose(node.state, goal)
                    for transition in proposals:
                        if self.nodes_expanded >= self.config.max_nodes_expanded:
                            break
                        self.nodes_expanded += 1
                        increment("search.nodes_expanded")
                        new_state, transition_result = transition.apply(node.state)
                        if not transition_result.passed:
                            continue

                        stack_result = self.verifier_stack.evaluate(new_state, transition)
                        child_depth = node.depth + 1
                        final = self.final_state_evaluator.evaluate(new_state, stack_result.score)
                        child_score = self._score(new_state, child_depth, stack_result.score)
                        child_signature = self._signature_for(new_state)

                        if self.config.enable_ts3 and child_signature:
                            if (
                                child_signature in set(node.path_signatures)
                                and self._has_no_progress(node.state, new_state)
                            ):
                                self._observe_ts3_loop(node, child_signature)
                                continue

                        if (
                            not stack_result.passed
                            or final.status in {FinalStatus.CONTRADICTORY, FinalStatus.UNSATISFIABLE}
                            or stack_result.score < self.config.verifier_score_threshold
                        ):
                            if final.status in {FinalStatus.CONTRADICTORY, FinalStatus.UNSATISFIABLE}:
                                self._observe_ts3_terminal(final.status.value)
                            continue

                        if self.config.enable_ts3 and child_signature and self.config.ts3_stagnation_penalty > 0:
                            if any(
                                n.state_signature == child_signature and n.state.version == new_state.version
                                for n in next_frontier
                                if n.state_signature is not None
                            ):
                                child_score -= self.config.ts3_stagnation_penalty

                        child = SearchNode(
                            state=new_state,
                            transition_history=[*node.transition_history, transition],
                            score=child_score,
                            depth=child_depth,
                            terminal_status=final.status.value,
                            state_signature=child_signature,
                            path_signatures=(
                                (*node.path_signatures, child_signature)
                                if child_signature
                                else node.path_signatures
                            ),
                        )
                        self._observe_ts3_state(
                            child,
                            final.status.value,
                            outgoing_transition_count=len(proposals),
                        )
                        self.max_depth_reached = max(self.max_depth_reached, child.depth)
                        if final.status == FinalStatus.VERIFIED:
                            self._observe_ts3_terminal(final.status.value)
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
            self._observe_ts3_terminal(best_evaluation.status.value)
            return self._result(best, best_evaluation)

    @staticmethod
    def search(
        initial_state: WorldStateMemory,
        proposer,
        verifier_stack,
        final_evaluator,
        config,
    ) -> SearchResult:
        return BeamSearch(
            proposer=proposer,
            verifier_stack=verifier_stack,
            final_state_evaluator=final_evaluator,
            config=config,
        ).run(initial_state)

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
                backend="beam",
            ),
            ts3_analysis=self._ts3.finalize() if self._ts3 is not None else None,
        )

    def _signature_for(self, state: WorldStateMemory) -> str | None:
        if not self.config.enable_ts3:
            return None
        return StateSignature.from_memory(state).value

    def _has_no_progress(self, before: WorldStateMemory, after: WorldStateMemory) -> bool:
        """No-progress means no material memory update happened."""
        return after.version == before.version

    def _observe_ts3_state(
        self,
        node: SearchNode,
        status: str,
        outgoing_transition_count: int,
    ) -> None:
        if self._ts3 is None or node.state_signature is None:
            return
        self._ts3.observe_state(
            SymbolicState(
                signature=node.state_signature,
                depth=node.depth,
                status=status,
                score=node.score,
                outgoing_transition_count=outgoing_transition_count,
            )
        )

    def _observe_ts3_terminal(self, status: str) -> None:
        if self._ts3 is None:
            return
        self._ts3.set_terminal_status(status)

    def _observe_ts3_loop(self, node: SearchNode, repeated_signature: str) -> None:
        if self._ts3 is None:
            return
        self._ts3.mark_loop_detected()
        if node.state_signature is None:
            return
        trajectory = Trajectory(
            symbolic_states=[
                SymbolicState(
                    signature=sig,
                    depth=index,
                    status=node.terminal_status or "UNKNOWN",
                    score=node.score,
                    outgoing_transition_count=0,
                )
                for index, sig in enumerate((*node.path_signatures, repeated_signature))
            ],
            transitions=[transition.type for transition in node.transition_history],
            terminal_status=node.terminal_status,
            loop_detected=True,
        )
        self._ts3.observe_trajectory(trajectory)
