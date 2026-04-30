"""Search node model."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcse.memory.world_state import WorldStateMemory
from vcse.transitions.state_transition import Transition


@dataclass
class SearchNode:
    state: WorldStateMemory
    transition_history: list[Transition] = field(default_factory=list)
    score: float = 0.0
    depth: int = 0
    terminal_status: str | None = None
    state_signature: str | None = None
    path_signatures: tuple[str, ...] = field(default_factory=tuple)
