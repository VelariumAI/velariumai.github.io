"""Monte Carlo Tree Search backend."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from vcse.memory.world_state import WorldStateMemory
from vcse.search.backend import SearchBackend
from vcse.search.node import SearchNode
from vcse.search.result import SearchResult, SearchStats
from vcse.ts3.signature import StateSignature
from vcse.ts3.symbolic_state import SymbolicState
from vcse.ts3.trajectory import Trajectory
from vcse.ts3.transient_analyzer import TransientAnalyzer
from vcse.verifier.final_state import FinalStatus


@dataclass
class MCTSNode:
    state: WorldStateMemory
    parent: "MCTSNode | None" = None
    transition: object | None = None
    children: list["MCTSNode"] = field(default_factory=list)
    visits: int = 0
    total_score: float = 0.0
    depth: int = 0
    terminal_status: str | None = None
    state_signature: str | None = None
    path_signatures: tuple[str, ...] = field(default_factory=tuple)
    untried_transitions: list[object] = field(default_factory=list)
    verifier_score: float = 0.0

    @property
    def avg_score(self) -> float:
        if self.visits == 0:
            return 0.0
        return self.total_score / self.visits


class MCTSSearch(SearchBackend):
    """Bounded verifier-centered MCTS over transition space."""

    def __init__(self, proposer, verifier_stack, final_state_evaluator, config) -> None:
        self.proposer = proposer
        self.verifier_stack = verifier_stack
        self.final_state_evaluator = final_state_evaluator
        self.config = config
        self.nodes_expanded = 0
        self.max_depth_reached = 0
        self.max_frontier_size = 0
        self.iterations = 0
        self._ts3: TransientAnalyzer | None = None

    @staticmethod
    def search(
        initial_state: WorldStateMemory,
        proposer,
        verifier_stack,
        final_evaluator,
        config,
    ) -> SearchResult:
        return MCTSSearch(
            proposer=proposer,
            verifier_stack=verifier_stack,
            final_state_evaluator=final_evaluator,
            config=config,
        ).run(initial_state)

    def run(self, initial_state: WorldStateMemory) -> SearchResult:
        self.nodes_expanded = 0
        self.max_depth_reached = 0
        self.max_frontier_size = 1
        self.iterations = 0
        self._ts3 = TransientAnalyzer() if self.config.enable_ts3 else None

        root_state = initial_state.clone()
        root_signature = self._signature_for(root_state)
        root = MCTSNode(
            state=root_state,
            depth=0,
            state_signature=root_signature,
            path_signatures=(root_signature,) if root_signature else tuple(),
        )
        root_eval, root_stack_score = self._evaluate_state(root.state, transition=None)
        root.terminal_status = root_eval.status.value
        root.verifier_score = root_stack_score
        root.untried_transitions = self._proposals(root.state)
        self._observe_ts3_state(root, outgoing=len(root.untried_transitions))

        best_node = root
        best_eval = root_eval

        if root_eval.status == FinalStatus.VERIFIED:
            self._observe_ts3_terminal(root_eval.status.value)
            return self._result(root, root_eval)

        for iteration in range(self.config.mcts_iterations):
            self.iterations = iteration + 1
            selected = self._select(root)
            expanded = self._expand(selected)
            leaf = expanded if expanded is not None else selected

            rollout_score, rollout_eval = self._simulate(leaf)
            self._backpropagate(leaf, rollout_score)

            if rollout_eval.status == FinalStatus.VERIFIED:
                best_node = leaf
                best_eval = rollout_eval
                self._observe_ts3_terminal(rollout_eval.status.value)
                break

            if self._is_better(leaf, rollout_eval, best_node, best_eval):
                best_node = leaf
                best_eval = rollout_eval

            frontier_size = self._leaf_count(root)
            self.max_frontier_size = max(self.max_frontier_size, frontier_size)

        if best_eval.status != FinalStatus.VERIFIED:
            best_eval, _ = self._evaluate_state(best_node.state, transition=None)
        self._observe_ts3_terminal(best_eval.status.value)
        return self._result(best_node, best_eval)

    def _select(self, root: MCTSNode) -> MCTSNode:
        node = root
        while True:
            if node.terminal_status in {FinalStatus.VERIFIED.value, FinalStatus.CONTRADICTORY.value, FinalStatus.UNSATISFIABLE.value}:
                return node
            if node.depth >= self.config.mcts_max_depth:
                return node
            if node.untried_transitions:
                return node
            if not node.children:
                return node
            node = max(node.children, key=lambda child: self._ucb1(child, node.visits))

    def _expand(self, node: MCTSNode) -> MCTSNode | None:
        if node.depth >= self.config.mcts_max_depth:
            return None
        if not node.untried_transitions:
            return None
        transition = node.untried_transitions.pop(0)
        self.nodes_expanded += 1
        new_state, transition_result = transition.apply(node.state)
        if not transition_result.passed:
            return None

        signature = self._signature_for(new_state)
        if self.config.enable_ts3 and signature and signature in set(node.path_signatures):
            if new_state.version == node.state.version:
                self._observe_ts3_loop(node, signature)
                return None

        final_eval, stack_score = self._evaluate_state(new_state, transition=transition)
        child = MCTSNode(
            state=new_state,
            parent=node,
            transition=transition,
            depth=node.depth + 1,
            terminal_status=final_eval.status.value,
            state_signature=signature,
            path_signatures=((*node.path_signatures, signature) if signature else node.path_signatures),
            verifier_score=stack_score,
        )
        child.untried_transitions = self._proposals(child.state)
        node.children.append(child)
        self.max_depth_reached = max(self.max_depth_reached, child.depth)
        self._observe_ts3_state(child, outgoing=len(child.untried_transitions))
        return child

    def _simulate(self, node: MCTSNode) -> tuple[float, object]:
        evaluation, verifier_score = self._evaluate_state(node.state, transition=None)
        if evaluation.status in {FinalStatus.VERIFIED, FinalStatus.CONTRADICTORY, FinalStatus.UNSATISFIABLE}:
            return self._score(node.state, node.depth, verifier_score, evaluation.status.value), evaluation

        simulated_state = node.state.clone()
        current_depth = node.depth
        current_eval = evaluation
        current_score = verifier_score
        for _ in range(self.config.mcts_rollout_depth):
            if current_depth >= self.config.mcts_max_depth:
                break
            proposals = self._proposals(simulated_state)
            if not proposals:
                break
            next_transition = self._best_rollout_transition(simulated_state, proposals, current_depth)
            if next_transition is None:
                break
            candidate_state, result = next_transition.apply(simulated_state)
            if not result.passed:
                break
            simulated_state = candidate_state
            current_depth += 1
            current_eval, current_score = self._evaluate_state(simulated_state, transition=next_transition)
            if current_eval.status in {FinalStatus.VERIFIED, FinalStatus.CONTRADICTORY, FinalStatus.UNSATISFIABLE}:
                break
        return self._score(simulated_state, current_depth, current_score, current_eval.status.value), current_eval

    def _best_rollout_transition(self, state: WorldStateMemory, transitions: list[object], depth: int):
        best_item = None
        best_score = float("-inf")
        for transition in transitions:
            candidate_state, result = transition.apply(state)
            if not result.passed:
                continue
            candidate_eval, candidate_stack = self._evaluate_state(candidate_state, transition=transition)
            score = self._score(candidate_state, depth + 1, candidate_stack, candidate_eval.status.value)
            if score > best_score:
                best_score = score
                best_item = transition
        return best_item

    def _backpropagate(self, node: MCTSNode, reward: float) -> None:
        current = node
        while current is not None:
            current.visits += 1
            current.total_score += reward
            current = current.parent

    def _evaluate_state(self, state: WorldStateMemory, transition) -> tuple[object, float]:
        stack_result = self.verifier_stack.evaluate(state, transition)
        final_eval = self.final_state_evaluator.evaluate(state, stack_result.score)
        return final_eval, stack_result.score

    def _proposals(self, state: WorldStateMemory) -> list[object]:
        goal = state.goals[0] if state.goals else None
        return list(self.proposer.propose(state, goal))

    def _ucb1(self, node: MCTSNode, parent_visits: int) -> float:
        if node.visits == 0:
            return float("inf")
        exploit = node.total_score / node.visits
        explore = self.config.mcts_exploration_weight * math.sqrt(math.log(max(parent_visits, 1)) / node.visits)
        return exploit + explore

    def _score(self, state: WorldStateMemory, depth: int, verifier_score: float, status: str) -> float:
        goal_progress = 0.0
        if state.goals:
            goal = state.goals[0]
            if state.find_claim(goal.subject, goal.relation, goal.object) is not None:
                goal_progress = self.config.goal_progress_weight
            elif goal.relation == "satisfies" and goal.object == "constraints":
                if goal.subject in state.symbol_bindings:
                    goal_progress = self.config.goal_progress_weight

        terminal_bonus = 0.0
        if status == FinalStatus.VERIFIED.value:
            terminal_bonus = 15.0
        elif status in {FinalStatus.CONTRADICTORY.value, FinalStatus.UNSATISFIABLE.value}:
            terminal_bonus = -12.0
        elif status == FinalStatus.INCONCLUSIVE.value:
            terminal_bonus = -0.25

        contradiction_penalty = self.config.contradiction_penalty if any(state.contradictions.values()) else 0.0
        depth_penalty = self.config.depth_penalty * depth
        uncertainty_penalty = 0.0 if goal_progress else self.config.uncertainty_penalty
        ts3_penalty = 0.0
        if self.config.enable_ts3:
            signature = self._signature_for(state)
            if signature is not None and self._ts3 is not None:
                # Soft-only TS3 guidance; never hard-prune progressing paths.
                ts3_penalty = 0.05 if signature in self._seen_signatures() else 0.0
        return (
            goal_progress
            + (self.config.verifier_score_weight * verifier_score)
            + terminal_bonus
            - contradiction_penalty
            - depth_penalty
            - uncertainty_penalty
            - ts3_penalty
        )

    def _is_better(self, node: MCTSNode, node_eval, best_node: MCTSNode, best_eval) -> bool:
        rank = {
            FinalStatus.VERIFIED: 4,
            FinalStatus.INCONCLUSIVE: 3,
            FinalStatus.CONTRADICTORY: 2,
            FinalStatus.UNSATISFIABLE: 1,
        }
        node_rank = rank.get(node_eval.status, 0)
        best_rank = rank.get(best_eval.status, 0)
        if node_rank != best_rank:
            return node_rank > best_rank
        return node.avg_score >= best_node.avg_score

    def _result(self, best_node: MCTSNode, evaluation) -> SearchResult:
        converted = SearchNode(
            state=best_node.state,
            transition_history=self._history(best_node),
            score=best_node.avg_score if best_node.visits else best_node.total_score,
            depth=best_node.depth,
            terminal_status=evaluation.status.value,
            state_signature=best_node.state_signature,
            path_signatures=best_node.path_signatures,
        )
        return SearchResult(
            best_node=converted,
            evaluation=evaluation,
            stats=SearchStats(
                nodes_expanded=self.nodes_expanded,
                max_depth_reached=self.max_depth_reached,
                terminal_status=evaluation.status.value,
                best_score=converted.score,
                max_frontier_size=max(self.max_frontier_size, 1),
                backend="mcts",
                iterations=self.iterations,
            ),
            ts3_analysis=self._ts3.finalize() if self._ts3 is not None else None,
        )

    def _history(self, node: MCTSNode) -> list[object]:
        history: list[object] = []
        current = node
        while current is not None and current.transition is not None:
            history.append(current.transition)
            current = current.parent
        return list(reversed(history))

    def _leaf_count(self, root: MCTSNode) -> int:
        queue = [root]
        leaves = 0
        while queue:
            current = queue.pop()
            if not current.children:
                leaves += 1
                continue
            queue.extend(current.children)
        return leaves

    def _signature_for(self, state: WorldStateMemory) -> str | None:
        if not self.config.enable_ts3:
            return None
        return StateSignature.from_memory(state).value

    def _observe_ts3_state(self, node: MCTSNode, outgoing: int) -> None:
        if self._ts3 is None or node.state_signature is None:
            return
        self._ts3.observe_state(
            SymbolicState(
                signature=node.state_signature,
                depth=node.depth,
                status=node.terminal_status or "UNKNOWN",
                score=node.avg_score,
                outgoing_transition_count=outgoing,
            )
        )

    def _observe_ts3_terminal(self, status: str) -> None:
        if self._ts3 is None:
            return
        self._ts3.set_terminal_status(status)

    def _observe_ts3_loop(self, node: MCTSNode, repeated_signature: str) -> None:
        if self._ts3 is None:
            return
        self._ts3.mark_loop_detected()
        trajectory = Trajectory(
            symbolic_states=[
                SymbolicState(
                    signature=sig,
                    depth=index,
                    status=node.terminal_status or "UNKNOWN",
                    score=node.avg_score,
                    outgoing_transition_count=0,
                )
                for index, sig in enumerate((*node.path_signatures, repeated_signature))
            ],
            transitions=[step.type for step in self._history(node)],
            terminal_status=node.terminal_status,
            loop_detected=True,
        )
        self._ts3.observe_trajectory(trajectory)

    def _seen_signatures(self) -> set[str]:
        if self._ts3 is None:
            return set()
        # Read from finalized reachability map through private object state would couple too hard.
        # Keep a lightweight approximation using no-op default.
        return set()
