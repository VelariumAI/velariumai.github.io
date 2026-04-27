"""Reachability analysis for TS3."""

from __future__ import annotations


class ReachabilityAnalyzer:
    """Tracks unique reachable states per depth."""

    def __init__(self) -> None:
        self._by_depth: dict[int, set[str]] = {}

    def observe(self, depth: int, signature: str) -> None:
        self._by_depth.setdefault(depth, set()).add(signature)

    def report(self) -> dict[int, int]:
        return {depth: len(signatures) for depth, signatures in sorted(self._by_depth.items())}
