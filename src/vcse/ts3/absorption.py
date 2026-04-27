"""Absorption analysis for TS3."""

from __future__ import annotations


TERMINAL_STATUSES = {"VERIFIED", "CONTRADICTORY", "UNSATISFIABLE"}
NONTERMINAL_STATUSES = {"INCONCLUSIVE", "UNKNOWN"}


class AbsorptionAnalyzer:
    """Counts terminal absorption outcomes across explored paths."""

    def __init__(self) -> None:
        self.verified_paths = 0
        self.contradictory_paths = 0
        self.unsatisfiable_paths = 0
        self.dead_end_paths = 0

    def record(self, status: str) -> None:
        if status == "VERIFIED":
            self.verified_paths += 1
        elif status == "CONTRADICTORY":
            self.contradictory_paths += 1
        elif status == "UNSATISFIABLE":
            self.unsatisfiable_paths += 1
        elif status in NONTERMINAL_STATUSES:
            self.dead_end_paths += 1

    def report(self) -> dict[str, float | int]:
        total = self.verified_paths + self.contradictory_paths + self.unsatisfiable_paths + self.dead_end_paths
        absorbed = self.verified_paths + self.contradictory_paths + self.unsatisfiable_paths
        return {
            "verified_paths": self.verified_paths,
            "contradictory_paths": self.contradictory_paths,
            "unsatisfiable_paths": self.unsatisfiable_paths,
            "dead_end_paths": self.dead_end_paths,
            "absorption_rate": (absorbed / total) if total else 0.0,
        }
