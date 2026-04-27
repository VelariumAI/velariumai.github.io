"""Transient symbolic state-space analyzer (TS3)."""

from __future__ import annotations

from dataclasses import dataclass

from vcse.ts3.absorption import AbsorptionAnalyzer
from vcse.ts3.loop_detector import LOOP_DETECTED, LoopDetector
from vcse.ts3.reachability import ReachabilityAnalyzer
from vcse.ts3.symbolic_state import SymbolicState
from vcse.ts3.trajectory import Trajectory
from vcse.perf import increment, stage


@dataclass(frozen=True)
class TS3AnalysisResult:
    loop_detected: bool
    stagnation_detected: bool
    terminal_status: str | None
    reachable_by_depth: dict[int, int]
    absorption_counts: dict[str, float | int]
    novelty_score: float
    contradiction_risk: float
    recommendation: str


class TransientAnalyzer:
    """Combines loop, reachability, and absorption signals."""

    def __init__(self) -> None:
        self.loop_detector = LoopDetector()
        self.reachability = ReachabilityAnalyzer()
        self.absorption = AbsorptionAnalyzer()
        self._seen_signatures: set[str] = set()
        self._observed_states = 0
        self._loop_detected = False
        self._terminal_status: str | None = None

    def observe_state(self, state: SymbolicState) -> None:
        with stage("ts3.observe_state"):
            self._observed_states += 1
            self._seen_signatures.add(state.signature)
            self.reachability.observe(state.depth, state.signature)
            increment("ts3.observed_states")

    def observe_trajectory(self, trajectory: Trajectory) -> None:
        with stage("ts3.observe_trajectory"):
            loop_signal = self.loop_detector.detect(trajectory)
            if loop_signal == LOOP_DETECTED:
                self._loop_detected = True
            if trajectory.terminal_status is not None:
                self._terminal_status = trajectory.terminal_status
                self.absorption.record(trajectory.terminal_status)

    def mark_loop_detected(self) -> None:
        self._loop_detected = True

    def set_terminal_status(self, status: str | None) -> None:
        self._terminal_status = status
        if status is not None:
            self.absorption.record(status)

    def finalize(self) -> TS3AnalysisResult:
        with stage("ts3.finalize"):
            reachable_by_depth = self.reachability.report()
            absorption_counts = self.absorption.report()
            novelty_score = (
                len(self._seen_signatures) / self._observed_states if self._observed_states else 0.0
            )
            contradiction_paths = float(absorption_counts.get("contradictory_paths", 0))
            unsat_paths = float(absorption_counts.get("unsatisfiable_paths", 0))
            terminal_paths = (
                float(absorption_counts.get("verified_paths", 0))
                + contradiction_paths
                + unsat_paths
            )
            contradiction_risk = ((contradiction_paths + unsat_paths) / terminal_paths) if terminal_paths else 0.0
            stagnation_detected = novelty_score < 0.5

            recommendation = "continue_exploration"
            if self._loop_detected:
                recommendation = "prune_looping_branches"
            elif contradiction_risk > 0.5:
                recommendation = "deprioritize_high_risk_branches"
            elif self._terminal_status in {"VERIFIED", "CONTRADICTORY", "UNSATISFIABLE"}:
                recommendation = "terminate_on_absorption"
            elif stagnation_detected:
                recommendation = "increase_novelty_or_adjust_proposer"

            return TS3AnalysisResult(
                loop_detected=self._loop_detected,
                stagnation_detected=stagnation_detected,
                terminal_status=self._terminal_status,
                reachable_by_depth=reachable_by_depth,
                absorption_counts=absorption_counts,
                novelty_score=novelty_score,
                contradiction_risk=contradiction_risk,
                recommendation=recommendation,
            )
