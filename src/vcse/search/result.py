"""Structured search result models."""

from __future__ import annotations

from dataclasses import dataclass

from vcse.memory.world_state import WorldStateMemory
from vcse.search.node import SearchNode
from vcse.transitions.state_transition import Transition
from vcse.verifier.final_state import FinalStateEvaluation


@dataclass(frozen=True)
class SearchStats:
    nodes_expanded: int
    max_depth_reached: int
    terminal_status: str
    best_score: float
    max_frontier_size: int


@dataclass(frozen=True)
class SearchResult:
    best_node: SearchNode
    evaluation: FinalStateEvaluation
    stats: SearchStats

    @property
    def state(self) -> WorldStateMemory:
        return self.best_node.state

    @property
    def transition_history(self) -> list[Transition]:
        return self.best_node.transition_history

    @property
    def score(self) -> float:
        return self.best_node.score

    @property
    def depth(self) -> int:
        return self.best_node.depth

    @property
    def terminal_status(self) -> str:
        return self.stats.terminal_status

    @property
    def nodes_expanded(self) -> int:
        return self.stats.nodes_expanded

    @property
    def max_depth_reached(self) -> int:
        return self.stats.max_depth_reached

    @property
    def best_score(self) -> float:
        return self.stats.best_score

    @property
    def max_frontier_size(self) -> int:
        return self.stats.max_frontier_size
