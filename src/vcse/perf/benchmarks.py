"""Profiling benchmarks helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkSample:
    run_index: int
    seconds: float


def summarize(samples: list[BenchmarkSample]) -> dict[str, float]:
    if not samples:
        return {"runs": 0, "avg_seconds": 0.0, "min_seconds": 0.0, "max_seconds": 0.0}
    values = [item.seconds for item in samples]
    return {
        "runs": float(len(values)),
        "avg_seconds": sum(values) / len(values),
        "min_seconds": min(values),
        "max_seconds": max(values),
    }
