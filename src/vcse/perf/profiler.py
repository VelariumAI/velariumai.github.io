"""High-level profiling wrapper."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter

from vcse.perf.traces import PerfTrace, activate_trace


@dataclass(frozen=True)
class ProfileResult:
    total_seconds: float
    stage_durations: dict[str, float]
    counters: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "total_seconds": self.total_seconds,
            "stage_durations": dict(self.stage_durations),
            "counters": dict(self.counters),
        }


@contextmanager
def profile_run() -> tuple[PerfTrace, list[float]]:
    trace = PerfTrace()
    started = perf_counter()
    with activate_trace(trace):
        end_holder: list[float] = []
        try:
            yield trace, end_holder
        finally:
            end_holder.append(perf_counter() - started)


def profile_result(trace: PerfTrace, total_seconds: float) -> ProfileResult:
    return ProfileResult(
        total_seconds=total_seconds,
        stage_durations=dict(sorted(trace.durations.items())),
        counters=dict(sorted(trace.counters.items())),
    )
