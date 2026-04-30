"""Search backend abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod

from vcse.memory.world_state import WorldStateMemory
from vcse.search.result import SearchResult


class SearchBackend(ABC):
    """Backend contract for state-space search implementations."""

    @staticmethod
    @abstractmethod
    def search(
        initial_state: WorldStateMemory,
        proposer,
        verifier_stack,
        final_evaluator,
        config,
    ) -> SearchResult:
        """Run search and return a structured result."""
        raise NotImplementedError
