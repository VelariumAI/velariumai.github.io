"""Base proposer interface."""

from __future__ import annotations

from typing import Protocol

from vcse.memory.world_state import Goal, WorldStateMemory
from vcse.transitions.state_transition import Transition


class BaseProposer(Protocol):
    def propose(self, memory: WorldStateMemory, goal: Goal | None = None) -> list[Transition]:
        ...
