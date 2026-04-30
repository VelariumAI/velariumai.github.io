"""Loop detection for TS3 trajectories."""

from __future__ import annotations

from vcse.ts3.trajectory import Trajectory


LOOP_DETECTED = "LOOP_DETECTED"


class LoopDetector:
    """Detect repeated state signatures in a trajectory."""

    def detect(self, trajectory: Trajectory) -> str | None:
        seen: set[str] = set()
        for state in trajectory.symbolic_states:
            if state.signature in seen:
                return LOOP_DETECTED
            seen.add(state.signature)
        return None

    def repeated_signature(self, signature: str, path_signatures: tuple[str, ...]) -> bool:
        return signature in set(path_signatures)
